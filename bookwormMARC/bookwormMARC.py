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
        if self.field is None or self.string is None:
            return dict()
        #LC classifications cannot include non-ascii characters, so we just coerce.
        lcclass = self.string.encode("ascii",'replace')
        #This regex defines an LC classification.
        mymatch = re.match(r"^(?P<lc1>[A-Z]+) ?(?P<lc2>[\.\d]+)", lcclass)
        if mymatch:
            returnt = {'lc0':lcclass[0],'lc1':mymatch.group('lc1'),'lc2':mymatch.group('lc2')}
            return returnt
        else:
            return(dict())
        
    def parse(self):
        if self.field is None:
            return dict()
        else:
            value = self.split()
            value['lc_class_from_lc'] = self.from_loc()
            return value
        
class F008(object):
    def __init__(self,record):
        self.data = record['008'].data
      
    def cataloging_source(self):
        return self.data[-1]
    
    def language(self):
        return self.data[35:38]
    
    def literary_form(self):
        return self.data[33]
    
    def government_document(self):
        return self.data[28]

    def target_audience(self):
        return self.data[22]
    
    def cntry(self):
        """
        The marc-country is in 15:18
        """
        return self.data[15:18]
    
    def marc_record_created(self):
        try:
            yy = self.data[0:2]
            mm = self.data[2:4]
            dd = self.data[4:6]
            # MARC fields are vulnerable to the Y2K bug.
            if int(yy) < 30:
                yyyy = "20" + yy
            else:
                yyyy = "19" + yy
            return "-".join([yyyy,mm,dd])
        except ValueError:
            return None
        
    def as_dict(self):
        value = dict()

        for attribute in [
            "marc_record_created"
            , "language"
            , "cntry" 
            , "language"
            , "cataloging_source"
            , "government_document"
         ]:
            value[attribute] = getattr(self,attribute)()

        return value
        
class Author(object):
    """
    A general purpose extraction class to handle a MARC author field.
    """
    def __init__(self,record):
        self.field = record
        self.parse_dates()
        
    def parse_dates(self):
        if self.field['d'] is None:
            self.birth=None
            self.death=None
            return            
        try:
            (self.birth,self.death) = self.field['d'].split("-")
        except ValueError:
            self.birth=None
            self.death=None
            return
        self.birth = normalize_year(self.birth)
        self.death = normalize_year(self.death)
    def name(self):
        return self.field.value()
    def as_dict(self,prefix=""):
        return {prefix + "name":self.name(),prefix + "birth":self.birth,prefix + "death":self.death}

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


# Extending some convenience functions onto pymarc.Record

class BRecord(pymarc.Record):
    def parse_authors(self):
        if hasattr(self,"authors"):
            return self.authors
        self.authors = []
        for field in self.get_fields('100'):
            author = Author(field)
            self.authors.append(author)
        return self.authors
    def parse_lc_class(self):
        classification = LCClass(self)
        return classification.parse()
    def parse_008(self):
        f008 = F008(self)
        return f008.as_dict()
    def date(self):
        """
        Field 260 is the first place to look for year. But this can be
        overridden by field 945y in Hathi metadata.
        """
        try:
            return normalize_year(self['260']['c'])
        except TypeError:
            return normalize_year(self.pubyear())
    def first_publisher(self):
        try:
            return self['260']['b']
        except TypeError:
            return None
        except KeyError:
            return None
    def first_place(self):
        try:
            return self['260']['a']
        except KeyError:
            return None
        except TypeError:
            return None
    def lccn(self):
        try:
            return self['010'].value()
        except:
            return None
    def cataloging_source(self):
        try:
            return self['040']['a']
        except KeyError:
            return None
        except TypeError:
            return None
        
    def author_age(self):
        try:
            self.parse_authors()
            return self.date() - self.authors[0].birth
        except:
            raise
    def first_author(self):
        authors = self.parse_authors()
        try:
            return authors[0].as_dict(prefix="first_author_")
        except IndexError:
            return {}
    
    def bookworm_dict(self):
        """
        Reformat the record as a dictionary for use with Bookworm.
        """
        master_record = dict()
        # Individual fields first.
        for field in ["date","title","first_publisher","first_place","cataloging_source"]:
            try:
                val = getattr(self,field)()
            except AttributeError:
                continue
            if val is not None:
                master_record[field] = val
        # Then methods that return dicts
        dicts = [self.parse_lc_class()
                 ,self.first_author()
                 ,self.parse_008()
                 ]
        for dicto in dicts:
            for (k,v) in dicto.iteritems():
                master_record[k] = v
        return master_record
        
    def hathi_bookworm_dicts(self):
        """
        Hathi does use one record for one book; instead, it stores many volumes under a record. 
        So we use field 974 to represent these.

        Also, Hathi has permalinks, which MARC records may not.
        """

        # First, grab the normal MARC info.
        master_record = self.bookworm_dict()

        if "date" in master_record:
            master_record["date_source"] = "008"
        
        for field in self.get_fields('974'):
            """
            Each entry in 974 is a separate scan of a record.
            In some cases, there may be loads of volumes with separate years.
            """
            local_info = dict()

            for (k,v) in master_record.iteritems():
                if v is not None:
                    local_info[k] = v
            
            for (k,v) in scan_data(field).iteritems():
                if v is not None:
                    if k == "additional_title":
                        local_info["title"] += ("--- " + v)
                        # Don't overwrite the title, just append with a triple dash.
                        continue
                    elif k=="date" and "date" in master_record:
                        # If we're overwriting the 008 field date, make a note of it
                        # and stash the other date. Unlikely to be used.
                        original = master_record["date"]
                        if original != v and v is not None:
                            local_info["date_source"] = "974"
                            local_info["alternidate"] = original
                    local_info[k] = v
            local_info["permalink"] = "https://babel.hathitrust.org/cgi/pt?id=" + local_info["filename"]
            try:
                local_info["searchstring"] = "<a href=%(permalink)s>%(author)s,<em>%(title)s</em> (%(date)s)" % local_info
            except KeyError:
                # There is no author; there should be a title, though
                local_info['searchstring'] = "<a href=%(permalink)s><em>%(title)s</em> (%(date)s)" % local_info
            yield local_info


_library_lookups = {u"mdp" : "University of Michigan", u"miu" : "University of Michigan", u"miua" : "University of Michigan", u"miun" : "University of Michigan", u"wu" : "University of Wisconsin", u"inu" : "Indiana University", u"uc1" : "University of California", u"uc2" : "University of California", u"pst" : "Penn State University", u"umn" : "University of Minnesota", u"nnc1" : "Columbia University", u"nnc2" : "Columbia University", u"nyp" : "New York Public Library", u"uiuc" : "University of Illinois", u"njp" : "Princeton University", u"yale" : "Yale University", u"chi" : "University of Chicago", u"coo" : "Cornell University", u"ucm" : "Universidad Complutense de Madrid", u"loc" : "Library of Congress", u"ien" : "Northwestern University", u"hvd" : "Harvard University", u"uva" : "University of Virginia", u"dul1" : "Duke University", u"ncs1" : "North Carolina State University", u"nc01" : "University of North Carolina", u"pur1" : "Purdue University", u"pur2" : "Purdue University", u"mdl" : "Minnesota Digital Library", u"usu" : "Utah State University Press", u"gri" : "Getty Research Institute", u"uiug" : "University of Illinois", u"psia" : "Penn State University", u"bc" : "Boston College", u"ufl1" : "University of Florida", u"ufl2" : "University of Florida", u"txa" : "Texas A&M University", u"keio" : "Keio University", u"osu" : "The Ohio State University", u"uma" : "University of Massachusets", u"udel" : "University of Delaware", u"caia" : "Clark Art Institute Library",u"pur":"Purdue University"}

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
    global _library_lookups
    try:
        library = _library_lookups[field['c'].lower()]
    except:
        library = field['c'].lower()
    return {
        "contributing_library":library,
        # Field 'd' is for when the rights were changed. Who cares?
        "rights_changed_date":"-".join([field['d'][:4], field['d'][4:6], field['d'][6:8]]),
        "scanner":field['s'],
        "filename":field['u'],
        "additional_title":field['z'],
        "date":normalize_year(field['y'])
    }

def subfield_reduce(subfields):
    value = []
    if isinstance(subfields,dict):
        subfields = [subfields]
    for subfield in subfields:
        value.append(subfield['code'])
        try:
            value.append(subfield['#text'])
        except KeyError:
            # Some records have a code but no text. I'm assuming that
            # means the space is just empty.
            value.append("")
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
            try:
                fld = Field(tag=field['tag'],subfields=subfield_reduce(subfields),indicators=[field['ind1'], field['ind2']])
            except KeyError:
                # Sometimes 035 fields
                raise
            rec.add_field(fld)
        except KeyError:
            try:
                fld = Field(tag=field['tag'],data=field['#text'])
                rec.add_field(fld)
            except KeyError:
                print field
                raise
    for field in entryRaw['controlfield']:
        try:
            fld = Field(tag=field['tag'],data=field['#text'])
        except KeyError:
            fld = Field(tag=field['tag'],data="")
        rec.add_field(fld)
    return rec
