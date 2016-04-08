import regex as re
import pymarc
import json
from pymarc import Record,Field


"""
Module extending pymarc to pull out metadata categories from
MARC records in a format that can be directly ingested into a
Bookworm.
"""

"""
TODO

1. Where is the serial/monograph distinction?

2. Integrate any additional fields from
   https://github.com/aristus/copymine-harvard/blob/master/marc.py

3. Further parsing of LC classification

4. LC subject headings from field 650.

5. Physical dimensions from field 300.

6. Make URL generation more general than just for Hathi.

7. Field 974['u'] is the correct filename for Hathi, but usually '001'
   or something will be better.
"""

class LCClass(object):
    def __init__(self, record):
        if record['050'] is not None:
            self.field = record['050']
        elif record['053'] is not None:
            self.field = record['053']
        else:
            self.field = None
        if self.field is not None:
            self.indicator1 = self.field.indicator1
            self.string = self.field['a']
    def from_loc(self):
        if not self.indicator1 in [0,"0",""]:
            return False
        return True
    def split(self):
        #LC classifications cannot include non-ascii characters, so we just coerce.
        lcclass = self.string.encode("ascii",'replace')
        #This regex defines an LC classification.
        mymatch = re.match(r"^(?P<lc1>[A-Z]+) ?(?P<lc2>\d+)", lcclass)
        if mymatch:
            returnt = {'lc0':lcclass[0],'lc1':mymatch.group('lc1'),'lc2':mymatch.group('lc2')}
            return returnt
        else:
            return(dict())

class F008(object):
    def __init__(self,record):
        self.f = record['008']
    def cntry(self):
        """
        Is this fields 12-15, or 14-17?
        """
        return self.f.value()[12:15]
    def govt_publication(self):
        # position 28
        pass
    def fiction(self):
        pass
        # Position 008

class Author(object):
    """
    A general purpose extraction class to handle a MARC author field.
    """
    def __init__(self,record):
        self.field = record
        self.dates()
        self.name()
    def dates(self):
        try:
            (self.birth,self.death) = self.field['d'].split("-")
        except ValueError:
            self.birth=None
            self.death=None
            return
        self.birth = normalize_year(self.birth)
        self.death = normalize_year(self.death)
    def name(self):
        self.name=self.field['a']
    def as_dict(self):
        return {"name":self.name(),"birth":self.birth,"death":self.death}

"""
From http://www.loc.gov/marc/bibliographic/bd260.html:
Subfield $c ends with a period (.), hyphen (-) for open-ended dates,
a closing bracket (]) or closing parenthesis ()). If subfield $c is
followed by some other subfield, the period is omitted.
The original REGEX:
YEAR_REGEX = re.compile(r'[\d]{4}')
^^ it's too simple, and only catches complete 4-digit dates.
"""
YEAR_REGEX = re.compile(r'([\d]{4}|[\d]{3}|([\d]{2}(?![ ]?cm)))')
"""
Okay, here are some possibilities that we have to deal with:
    186-?]
    [185-?]
    [189?]
    187?]
    184[5?]
    [186-]
    c19         -- is the 19th century, or a misinterpretaion of 260$c19 ?
    cl9l6]
    M. D. LXXIII.
    M. D. LXVIII.
    M.DCC.LXI.
    191
    18--
    18 -19
    MDCCLXXIX.
    MDCCLXX-LXXXIX]
    19 cm.        these get matched wrong
    5682 [1921]    as does this...
This new function covers the 2, 3, and 4 digit segmented cases.
Now to convert roman numerals...
There seem to be a number of cases of `l` being substituted for `1`.
"""

def normalize_year(year_string):
    """ Attempt to normalize a year string.
    Returns the most recent year that can be extracted
    from year_string as an integer.
    """
    # if not year_string:
    #     return None
    # matches = YEAR_REGEX.findall(year_string)

    # return max(map(int, matches)) if matches else None

    if not year_string:
        return None

    # l9l6 --> 1916
    year_string = year_string.replace('l', '1')

    matches = YEAR_REGEX.findall(year_string)
    if not matches:
        return None

    matches = map(lambda x: x[0], matches)
    y = max(matches, key=lambda x: len(x))
    y = "{:0<4}".format(y) # ljust w/ 0s

    return int(y)


# Monkeypatching some convenience functions onto pymarc.Record

class BRecord(pymarc.Record):
    def parse_authors(self):
        if hasattr(self,"authors"):
            return self.authors
        self.authors = []
        for field in self.get_fields('100'):
            author = Author(field)
            self.authors.append(author)
        return self.authors

    def date(self):
        """
        Field 260 is the first place to look for year. But this can be
        overridden by field 945y in Hathi metadata.
        """
        return normalize_year(self['260']['c'])
    def first_publisher(self):
        return self['260']['b']
    def first_place(self):
        return self['260']['a']
    def lccn(self):
        try:
            return self['010'].value()
        except:
            raise
    def author_age(self):
        try:
            self.parse_authors()
            return self.date() - self.authors[0].birth
        except:
            raise
    def first_author(self):
        authors = self.parse_authors()
        try:
            return authors[0].field.value()
        except IndexError:
            return None
    def cntry(self):
        """
        The country field from MARC 008.
        Can be combined with publication place to locate any book quite
        precisely.

        I don't understand why this shows up in 12:15; sources say it should be
        in bytes 14:17
        """
        a = F008(self)
        return a.cntry()
    def bookworm_dicts(self):
        master_record = dict()
        for field in ["date","title","first_author","first_publisher","first_place"]:
            try:
                val = getattr(self,field)()
            except AttributeError:
                continue
            if val is not None:
                master_record[field] = val

        for field in self.get_fields('974'):
            """
            Each entry in 974 is a separate scan of a record.
            In some cases, there may be loads of volumes with separate years.
            """
            local_info = dict()

            for (k,v) in master_record.iteritems():
                if v is not None:
                    # Note this can overwrite publication year.
                    local_info[k] = v
            for (k,v) in scan_data(field).iteritems():
                if v is not None:
                    if k == "additional_title":
                        local_info["title"] += ("-- " + v)
                    else:
                        local_info[k] = v
            try:
                local_info['searchstring'] = "<a href=%(filename)s>%(author)s,<em>%(title)s</em> (%(date)s)" % local_info
            except KeyError:
                # There is no author; there should be a title, though
                local_info['searchstring'] = "<a href=%(filename)s><em>%(title)s</em> (%(date)s)" % local_info
            yield local_info

def scan_data(field):
    """
    field: a 974 field parsed by pymarc.Field.

    HathiTrust records use a special MARC field, 974, to store additional data.
    This extracts some useful information, including:
    1. Scanning library (eg, Michigan)
    2. Scanning partner (eg, Google)
    3. Additional titles (eg, volume numbers)
    4. Date (for serial volumes bundled under a single MARC record)
    """
    return {
        "libraryB":field['b'],
        "libraryC":field['c'],
        "ingest_date":"-".join([field['d'][:4], field['d'][4:6], field['d'][6:8]]),
        "scanner":field['s'],
        "filename":field['u'],
        "additional_title":field['z'],
        "date":field['y']
    }

def subfield_reduce(subfields):
    value = []
    if isinstance(subfields,dict):
        subfields = [subfields]
    for subfield in subfields:
        value.append(subfield['code'])
        value.append(subfield['#text'])
    return value

def parse_record(entry):
    """
    Create a pymarc.Record instance from a row in the DPLA Hathi dump.
    pymarc's onboard MarcJSON parser assumes a slightly different format
    than the DPLA/Hathi one (tuples instead of keyed dictionaries) so I've
    just altered the record ingest code from there.
    """
    entryRaw = json.loads(entry)["_source"]["originalRecord"]
    rec = BRecord()
    rec.leader = entryRaw['leader']
    for field in entryRaw['datafield']:
        try:
            subfields = field['subfield']
            fld = Field(tag=field['tag'],subfields=subfield_reduce(subfields),indicators=[field['ind1'], field['ind2']])
            rec.add_field(fld)
        except KeyError:
            try:
                fld = Field(tag=field['tag'],data=field['#text'])
                rec.add_field(fld)
            except KeyError:
                print field
                raise
    for field in entryRaw['controlfield']:
        fld = Field(tag=field['tag'],data=field['#text'])
        rec.add_field(fld)
    return rec
