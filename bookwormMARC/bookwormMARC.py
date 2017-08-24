import regex as re
import pymarc
import json
from pymarc import Record,Field
import logging
import os
import csv


"""
Module extending pymarc to pull out metadata categories from
MARC records in a format that can be directly ingested into a
Bookworm.
"""

"""
TODO

2. Integrate any additional fields from
   https://github.com/aristus/copymine-harvard/blob/master/marc.py

3. Further parsing of LC classification

4. LC subject headings from field 650.

5. Physical dimensions from field 300.

6. Make URL generation more general than just for Hathi.

7. Field 974['u'] is the correct filename for Hathi, but usually '001'
   or something will be better.
"""

with open(os.path.join(os.path.dirname(__file__), 'data', 'language-codes.csv'), mode='r') as f:
    lang_lookup = dict(csv.reader(f))
    
with open(os.path.join(os.path.dirname(__file__), 'data', 'country-codes.csv'), mode='r') as f:
    cntry_lookup = dict(csv.reader(f))

# Encoding unexpected values where the intent is clear
for bad_code in ['xxx', '|||', '   ']:
    lang_lookup[bad_code] = 'Unknown'
for bad_code in ['xxx', '|||', '###', '   ']:
    cntry_lookup[bad_code] = 'Unknown'
    
def integerize(string,allow_cutter_numbers=True):
    """
    Turns a number into a string.
    If the number is a Cutter number like "A435", extracts the letter part into a
    tuple so the result is ("A",435).

    This preserves sortability.
    """
    if string is None:
        return None
    try:
        return int(string)
    except ValueError:
        return (string[0],int(string[1:]))

class LCCallNumber(list):
    """
    An LCC is a tuple of six elements. (The exact number of elements is subject to change in later revisions.)

    This means that they can be sorted and compared in a variety of useful ways
    that the raw strings can not.
    """
    def __init__(self,string):
        cleaned = self.clean(string)
        components = self.split_number(cleaned)
        return list.__init__(self,components)


    def __cmp__(self,objecta):
        print self
        print objecta
        a = tuple(self)
        b = tuple(objecta)
        if a > b: return 1
        if a == b: return 0
        if a < b: return -1
    
    def subsumes(self,other_call_number):
        """
        A call number can trail off into vagueness with a number of None
        elements.

        So "AK 101" is taken to subsume "AK 101.E35".

        Any field includes itself. So be careful of infinite recursion.

        I don't currently use this code.
        """
        truthiness = True
        for (a,b) in zip(self,other_call_number):
            if a != b:
                if a is not None:
                    truthiness = False
        return truthiness
                 
    def next_unincluded_class(self):
        vals = [i for i in self]
        vals.reverse()

        # Bump recursively, because some tuple elements
        # are tuple themselves (such as Cutter Numbers)
        
        def bump(tuplee):
            listed = list(tuplee)
            listed.reverse()
            for (i, element) in enumerate(listed):
                if element is None:
                    continue
                if isinstance(element,int):
                    listed[i] = element + 1
                    break
                if isinstance(element,str):
                    listed[i] = increment(element)
                    break
                if isinstance(element,tuple):
                    listed[i] = bump(element)
                    break

            listed.reverse()
            return tuple(listed)
        
        new_version = bump(self)
        # reclass
        phony = self.__class__("A")
        for (k,v) in enumerate(new_version):
            phony[k] = v
        return phony
        

    @staticmethod
    def integerize(string,allow_cutter_numbers=True):
        """
        Turns a string into a sortable number.
        If the number is a Cutter number, extracts the letter part.
        Doesn't handle decimals.
        """
        if string is None:
            return None
        try:
            return int(string)
        except ValueError:
            return (string[0],int(string[1:]))
        
    @staticmethod
    def split_number(string):
        alpha     = r'(?P<classalph>[A-Z]+)'
        class_number = r'((?P<classno_whole>\d+)(\.(?P<classno_decimal>\w?\d+)?)?)?'
        date1     = r'( ?(?P<date1>\d\w\w+))?'
        cutter1   = r'( ?\.?(?P<cutter1>[A-Z]\d+))?'
        date2     = r'(?P<date2>[\. ]\d\w+)?'
        cutter2   = r'( ?\.?(?P<cutter2>[A-Z]\d+))?'        
        # At this point, I punt. To extend, see
        # https://www.oclc.org/bibformats/en/0xx/050.html
        therest   = r'(?P<therest>[^\t]+)?'
        
        full_regex = alpha + " ?" + class_number + date1 + cutter1 + date2 + cutter2 + therest

        mymatch = re.match(full_regex,string)
        integerize = LCCallNumber.integerize
        
        try:
            return [mymatch.group('classalph'),
                integerize(mymatch.group('classno_whole')),
                integerize(mymatch.group('classno_decimal')),
                mymatch.group('date1'),                
                integerize(mymatch.group('cutter1')),
                mymatch.group('date2'),
                integerize(mymatch.group('cutter2')),
                mymatch.group('therest')
            ]
        
        except AttributeError:
            raise TypeError("Unparseable LC Number: '%s'" % string)
            
    @staticmethod
    def clean(string):
        string = string.encode("ascii","replace")
        string = string.replace("(","")
        string = string.replace(")","")
        return string

def increment(string):
    """
    for "A", return "B"
    for "AC", return "AD"
    After AZ comes `A[`. That's OK for my purposes.    
    """
    
    rest = string[:-1]    
    last = chr(ord(string[-1]) + 1)
    #print rest+last
    return rest + last

def lcc_range(string):
    """
    Takes a string, returns a tuple of two LCClassNumbers, the start and
    end of the range.
    """
    string = string.encode("ascii","replace")
    string = string.replace("(","")
    string = string.replace(")","")
    if string.endswith("A-Z"):
        # TMI in the schedules when they're alphabetical.
        # I don't care.
        string.replace("A-Z","")

    if "-" not in string:
        # A range of self length.
        return (LCCallNumber(string), LCCallNumber(string))

    parts = string.split("-")
    if re.search(r"^\d",parts[1]):
        header = re.sub("^([A-Z]+).*",r"\1",parts[0])
    elif re.search(r"^\.",parts[1]):
        header = re.sub(r"^([A-Z]+\d)+\..*",r"\1",parts[0])
    elif re.search(r"^[A-Z]",parts[1]):
        header = re.sub(r"^([A-Z]+\d)+\..[A-Z]*",r"\1.",parts[0])            
    else:
        header = " "

    parts[1] = header + parts[1]
    return (
        LCCallNumber(parts[0]),
        LCCallNumber(parts[1])
    )



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

        
class Leader(object):
    """
    Parses elements out of the MARC leader.
    """
    def __init__(self,record):
        self.data = record.leader

    def resource_type(self):
        """
        I use the leader to determine the resource type according to this
        table from MARC, except that I separate "manuscripts" from "books"

            Dependencies

            Field 008/18-34 Configuration
            If Leader/06 = a and Leader/07 = a, c, d, or m: Books
            If Leader/06 = a and Leader/07 = b, i, or s: Continuing Resources
            If Leader/06 = t: Books
            If Leader/06 = c, d, i, or j: Music
            If Leader/06 = e, or f: Maps
            If Leader/06 = g, k, o, or r: Visual Materials
            If Leader/06 = m: Computer Files
            If Leader/06 = p: Mixed Materials

        """
        L6 = self.data[6]
        L7 = self.data[7]
        if L6 == "a" and L7 in ["a","c","d","m"]:
            return "book"
        if L6 == "a" and L7 in ["b","i","s"]:
            return "serial"
        if L6 == "t":
            return "manuscript"
        if L6 in ["c","d","i","j"]:
            return "music"
        if L6 in ["e","f"]:
            return "map"
        if L6 in ["g","k","o","r"]:
            return "visual materials"
        if L6=="m":
            return "computer files"
        if L6=="p":
            return "mixed materials"
        return "not present"
    
       
class F008(object):
    def __init__(self, record, resource_type="unknown", warn_bad_value=True):
        '''
        
        resource_type: For better handling of fields specific to a resource type like music or books.
        
        warn_bad_value: For closed class fields, warn when the value does not fit the lookup and return a
            code. If False, throws an error.
        
        '''
        self.data = record['008'].data
        self.resource_type = resource_type
        self.warn_bad_value = warn_bad_value

        if len(self.data) != 40:
            self.correct_short()
            
        if 'U+' in self.data:
            logging.warn('Malformed 008 field: %s' % self.data)
            self.correct_malformed()

    def correct_short(self):
        l = len(self.data)
        if len(self.data) == 38:
            # Assume 38 and 39 are missing
            self.data += '|u'
        elif len(self.data) == 39:
            # Assume 39 is missing
            self.data += 'u'
        else:
            # throw your hands up and give up
            # Actually, right pad to 40 chars, then pass to correct_malformed
            logging.error("008 short in unaccountable way: %s" % self.data)
            self.data = self.data.ljust(40, ' ')
            self.correct_malformed()
        
    def correct_malformed(self):
        ''' Go backwards, and reset unexpected codes to 'Unknown' '''
        errs = 0
        if self.data[33] not in self.lit_lookup:
            errs += 1
            self.data = self.data[:33] + 'u' + self.data[34:]

        if self.data[28] not in self.gov_lookup:
            errs += 1
            self.data = self.data[:28] + ' ' + self.data[29:]
            
        if self.data[22] not in self.target_audience_lookup:
            errs += 1
            self.data = self.data[:22] + '#' + self.data[23:]
            
        if errs >= 2:
            # Set lang to 'No information provided'
            self.data = self.data[:35] + '###' + self.data[39:]

    def cataloging_source(self):
        return self.data[-1]
    
    def language(self):
        lcode = self.language_code()
        try:
            return lang_lookup[lcode]
        except:
            if self.warn_bad_value:
                logging.warn("No language for %s, returning just the MARC code" % lcode)
                return lcode
            else:
                raise
    
    def language_code(self):
        return self.data[35:38]
    
    lit_lookup = {
        "0": "Not fiction",
        "1": "Fiction",
        "d": "Dramas",
        "e": "Essays",
        "f": "Novels",
        "h": "Humor, satires, etc.",
        "i": "Letters",
        "j": "Short stories",
        "m": "Mixed forms",
        "p": "Poetry",
        "s": "Speeches",
         "u": "Unknown",
        "|": "No attempt to code",
        " ": "Unknown"
    }

    def literary_form(self):
        code = self.data[33]
        
        if self.resource_type in ['serials']:
            return "Undefined"
        
        try:
            return self.lit_lookup[code]
        except:
            if self.warn_bad_value:
                logging.warn("No literary form for code %s, returning just the MARC code" % code)
                return code
            else:
                raise
        
       
    gov_lookup = {'#': 'Not a government publication',
                 'a': 'Autonomous or semi-autonomous component',
                 'c': 'Multilocal',
                 'f': 'Federal/national',
                 'i': 'International intergovernmental',
                 'l': 'Local',
                 'm': 'Multistate',
                 'o': 'Government publication-level undetermined',
                 's': 'State, provincial, territorial, dependent, etc.',
                 'u': 'Unknown if item is government publication',
                 'z': 'Other',
                 '|': 'No attempt to code',
                 ' ': 'Unknown'
                 }
        
    def government_document(self):
        code = self.data[28]
        try:
            if self.resource_type in ["mixed materials", "music"]:
                return "Undefined"
            else:
                return self.gov_lookup[code]
        except:
            if self.warn_bad_value:
                logging.warn("Bad government lookup. Often an indicator of malformed 008: %s" % code)
                return "Unknown"
            else:
                raise

    target_audience_lookup = {
        "#": "Unknown or not specified",
        "a": "Preschool",
        "b": "Primary",
        "c": "Pre-adolescent",
        "d": "Adolescent",
        "e": "Adult",
        "f": "Specialized",
        "g": "General",
        "j": "Juvenile",
        "|": "No attempt to code",
        " ": "Unknown"
    }
    
    
    def target_audience(self):
        code = self.data[22]
        if self.resource_type in ['maps', 'mixed materials']:
            return "Undefined"
        try:
            return self.target_audience_lookup[code]
        except KeyError:
            if self.warn_bad_value:
                logging.warn("Bad target audience, %s" % code)
                return "Unknown or not specified"
            else:
                raise
    
    def country(self):
        code = self.cntry_code()
        
        results = dict()

        if code.strip() not in cntry_lookup:
            return results

        state_code, cntry_code = code[:2], code[2]

        cntry_code_ref = dict(u='USA', c='Canada', k='United Kingdom', a='Australia', r='Soviet Union')
        if cntry_code in cntry_code_ref:
            try:
                results['publication_country'] = cntry_code_ref[cntry_code]
                if state_code not in ['xx', '  ']:
                    # '  x' shouldn't be valid, but the intent seems clear enough to assume the same as 'xx#'
                    results['publication_state'] = cntry_lookup[code]
            except:
                if self.warn_bad_value:
                    logging.warn("Illegal country sub-division for %s" % code)
                    return results
                else:
                    raise
        else:
            try:
                results['publication_country'] = cntry_lookup[code.strip()]
            except:
                if self.warn_bad_value:
                    logging.warn("Illegal publication country for %s" % code)
                    results['publication_country'] = code
                    return results
                else:
                    raise
        return results

    def cntry_code(self):
        """
        The marc-country is in 15:18
        """
        code = self.data[15:18]
        if code in ['|||']:
            code = 'xx '
        return code
    
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
            , "cataloging_source"
            , "government_document"
            , "literary_form"
            , "target_audience"
         ]:
            try:
                value[attribute] = getattr(self,attribute)()
            except IndexError:
                # There are some malformed JSON even here.
                pass
        
        # Attributes that return a dictionary with multiple keys
        for attribute in [
            "country"
         ]:
            try:
                result = getattr(self,attribute)()
                for key in result:
                    value[key] = result[key]
            except:
                pass
            
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
        """
        THIS DOESN"T YET HANDLE CORPORATE AUTHORS
        (FIELD 110)
        """
        
        if hasattr(self,"authors"):
            return self.authors
        self.authors = []
        for field in self.get_fields('100'):
            author = Author(field)
            self.authors.append(author)
        return self.authors
    
    def parse_lc_class(self, **kwargs):
        classification = LCClass(self)
        return classification.parse()
    
    def parse_008(self, **kwargs):
        f008 = F008(self, resource_type=self.resource_type(), **kwargs)
        return f008.as_dict()
    
    def record_date(self):
        """
        Field 260 is the first place to look for year. But this can be
        overridden by field 945y in Hathi metadata.
        """
        try:
            y =  normalize_year(self['260']['c'])
            if y is None:
                y = normalize_year(self.pubyear())                
        except TypeError:
            # when there is no self['260']
            y = normalize_year(self.pubyear())
        
        return y
        
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
    def resource_type(self):
        leader = Leader(self)
        return leader.resource_type()
    
    def author_age(self):
        try:
            self.parse_authors()
            return self.date() - self.authors[0].birth
        except:
            raise

    def subject_places(self):
        fields = []
        for field in self.get_fields('043'):
            if 'a' in field:
                fields.append(field['a'])
        return fields

    def serial_killer_guess(self):
        """
        Implements the Aiden-Michel serial-killer algorithm as described at

        http://dx.doi.org/10.1126/science.1199644

        http://science.sciencemag.org.ezproxy.neu.edu/content/331/6014/176.figures-only.

        I don't think this is likely to be that useful for most users;
        it's here to test the algorithm.
        """

        titles = set(re.findall(r"\w+",self.title().lower()))
        try:
            author = set(re.findall("\w+",self.first_author()["first_author_name"].lower()))
        except KeyError:
            author = set([])
            
        title_blacklist = set(["advances", "almanac", "annual", "bibliography", "biennial", "bulletin", "catalog", "catalogue", "census", "conference", "conferences", "congress", "congressional", "digest", "digest", "directory", "hearings", "index", "journal", "magazine", "meeting", "meetings", "monthly", "papers", "periodical", "proceedings", "progress", "quarterly", "report", "reports", "review", "revista", "serial", "society", "subcommittee", "symposium", "transactions", "volume", "yearbook", "yearly"])
        
        author_blacklist = set(["the", "of", "and", "administration", "congress", "international", "national", "federal", "state", "american", "british", "consortium", "university", "office", "america", "united", "states", "britain", "ireland", "canada", "australia", "institute", "research", "committee", "subcommittee", "court", "association", "foundation", "board", "bureau", "house", "senate", "dept", "department", "state", "council", "club", "school", "network", "online", "company", "co", "us", "u.s.", "survey", "agency", "academy", "commission", "press", "publishing", "publishers", "academic", "cambridge", "sciencedirect", "kluwer", "oxford", "interscience", "library", "on", "society", "service", "affairs", "division", "commerce", "public", "foreign", "government", "agriculture", "science", "engineers", "stanford", "medical", "energy", "laboratory", "economic", "geological", "assembly", "alabama", "alaska", "american", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "columbia", "district", "florida", "georgia", "guam", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "hampshire", "jersey", "mexico", "york", "ohio", "oklahoma", "oregon", "pennsylvania", "north", "south", "tennessee", "texas", "utah", "vermont", "wisconsin", "wyoming"])

        if len(titles.intersection(title_blacklist)) + len(author.intersection(author_blacklist)):
            return "serial"
        return "book"

    
    def first_author(self, **kwargs):
        authors = self.parse_authors()
        try:
            return authors[0].as_dict(prefix="first_author_")
        except IndexError:
            return {}
    
    def bookworm_dict(self, **kwargs):
        """
        Reformat the record as a dictionary for use with Bookworm.

        This does not include Hathi-specific fields.
        """
        master_record = dict()
        # Individual fields first.
        for field in ["record_date","title","first_publisher","first_place","cataloging_source","subject_places","resource_type","serial_killer_guess"]:
            try:
                val = getattr(self,field)()
            except AttributeError:
                continue
            if val is not None and val!=[]:
                master_record[field] = val
            if val is None and field == "record_date":
                # We need a date, even if we don't know it.
                master_record[field] = val
        # Then methods that return dicts
        dicts = [self.parse_lc_class(**kwargs)
                 ,self.first_author(**kwargs)
                 ,self.parse_008(**kwargs)
                 ]
        for dicto in dicts:
            for (k,val) in dicto.iteritems():
                if val is not None and val != []:
                    master_record[k] = val
        return master_record
        
    def hathi_bookworm_dicts(self, **kwargs):
        """
        Hathi does use one record for one book; instead, it stores many volumes under a record. 
        So we use field 974 to represent these.

        Also, Hathi has permalinks, which MARC records may not.
        """

        # First, grab the normal MARC info.
        master_record = self.bookworm_dict(**kwargs)
        
        for field in self.get_fields('974'):
            """
            Each entry in 974 is a separate scan of a record.
            In some cases, there may be loads of volumes with separate years.
            """
            local_info = dict()

            for (k,v) in master_record.iteritems():
                local_info[k] = v
        
            for (k,v) in scan_data(field).iteritems():
                if v is not None:
                    if k == "additional_title":
                        try:
                            local_info["title"] += ("--- " + v)
                        except KeyError:
                            local_info["title"] = v
                        # Don't overwrite the title, just append with a triple dash
                        continue
                    local_info[k] = v
            local_info["permalink"] = "https://babel.hathitrust.org/cgi/pt?id=" + local_info["filename"]

            try:
                if local_info["item_date"] and local_info["item_date"] is not None:
                    local_info["date"] = local_info["item_date"]
                else:
                    local_info["date"] = local_info["record_date"]
            except KeyError:
                local_info["date"] = local_info["record_date"]
                
            try:
                local_info["searchstring"] = "<a href=%(permalink)s>%(author)s,<em>%(title)s</em> (%(date)s)" % local_info
                
            except KeyError:
                try:
                # There is no author; there should be a title, though
                    local_info['searchstring'] = "<a href=%(permalink)s><em>%(title)s</em> (%(date)s)" % local_info
                except KeyError:
                    local_info['searchstring'] = "<a href=%(permalink)s>[No title] (%(date)s)" % local_info
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
        code = field['u'].split(".",1)[0]
        library = _library_lookups[code]
    except KeyError:
        library = "Unknown"
    return {
        "contributing_library":library,
        # Field 'd' is for when the rights were changed. Who cares?
        "rights_changed_date":"-".join([field['d'][:4], field['d'][4:6], field['d'][6:8]]),
        "scanner":field['s'],
        "filename":field['u'],
        "additional_title":field['z'],
        "item_date":normalize_year(field['y'])
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


