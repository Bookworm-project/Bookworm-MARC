import tarfile
import cStringIO
import random
import sys
import pymarc
from bookwormMARC import BRecord
import logging
import json
import bz2

"""
These define methods specific to Hathi Trust MARC record parser.
"""

def obj_to_marc(jobj):
    """"
    Coerces a dict into a MARC object.
    """
    rec = BRecord()
    rec.leader = jobj['leader']
    for field in jobj['fields']:
        k,v = list(field.items())[0]
        if 'subfields' in v and hasattr(v,'update'):
            # flatten m-i-j dict to list in pymarc
            subfields = []
            for sub in v['subfields']:
                for code,value in sub.items():
                    subfields.extend((code,value))
            fld = pymarc.Field(tag=k,subfields=subfields,indicators=[v['ind1'], v['ind2']])
        else:
            fld = pymarc.Field(tag=k,data=v)
        rec.add_field(fld)
    return rec

class All_Hathi(object):
    """
    A generator that will yield, one at a time, a bookworm-suitable JSON file for every document in the Hathi Trust.
    """
    def __init__(self,root = "/drobo/hathi_metafiles"):
        self.files = []
        if not root.endswith("/"):
            # I always forget to end dirs with a slash.
            root = root + "/"
        base_names = ["meta_ic.json.bz2","meta_pd_google.json.bz2",
                      "meta_pd_open_access.json.bz2","meta_restricted.json.bz2"]
        for name in base_names:
            self.files.append(root + name)
        
    def __iter__(self):
        """
        The iterator goes through, in descending depth:
        1. Every giant file of the Hathi dumps;
        2. Every record in each file;
        3. Every item in each record.
        """
        for fn in self.files:
            sys.stdout.write("Reading fn\n")
            file = bz2.BZ2File(fn)
            for line in file:
                record = obj_to_marc(json.loads(line))
                for vol in record.hathi_bookworm_dicts():
                    yield vol
                
def hathi_item_yielder():
    records = hathi_record_yielder()
    for record in records:
        for item in record.hathi_bookworm_dicts():
            yield item
    

def hathi_record_yielder(
        sample_files=100,
        sample_records=100,
        ):
    """
    Returns a generator that cycles, one at a time, through all the records.


    We're reading the full DPLA dump out of the tarfile, and then definnig a generator object from a yielding function.

    Each object returned by the generator is a record from the great pymarc utility.

    It has a native method for parsing multirecord marcxml, but that relies on reading the entire 
    giant files into the DOM. That's a waste of time, so I just chunk the records out by hand in a non-elegant way.
    This method may not work on non-Hathi MARC files if they use different patterns of newlines.
    """
    
    hathi_records = tarfile.open(tarfile_location)    
    for file in hathi_records:
        if file.name.endswith(".xml") and random.random()<=(sample_files/float(100)):    
            logging.info("Parsing new XML file " + file.name)
            buffer = ""
            in_record = False
            for line in hathi_records.extractfile(file):
                if "<record>" in line:
                    if random.random()<=(sample_records/float(100)):
                        in_record=True
                if in_record:
                    buffer += line
                if "</record>" in line and in_record:
                    in_record = False
                    records = pymarc.parse_xml_to_array(cStringIO.StringIO(buffer))
                    buffer = ""
                    for record in records:
                        record.__class__ = BRecord
                        yield record


def hathi_record_yielder(
        filenames,
        sample_files=100,
        sample_records=100
        ):
    """Returns a generator that cycles, one at a time, through all the records.

    We're reading the full DPLA dump out of the tarfile, and then
    definnig a generator object from a yielding function.

    Each object returned by the generator is a record from the great
    pymarc utility.

    It has a native method for parsing multirecord marcxml, but that
    relies on reading the entire giant files into the DOM. That's a
    waste of time, so I just chunk the records out by hand in a
    non-elegant way.  This method may not work on non-Hathi MARC files
    if they use different patterns of newlines.
    """
   
#    hathi_records = tarfile.open(tarfile_location)    
    for file in filenames:
        if file.endswith(".xml") and random.random()<=(sample_files/float(100)):    
            logging.info("Parsing new XML file " + file)
            buffer = ""
            in_record = False
            for line in open(file,"r"):#hathi_records.extractfile(file):
                if "<record>" in line:
                    if random.random()<=(sample_records/float(100)):
                        in_record=True
                if in_record:
                    buffer += line
                if "</record>" in line and in_record:
                    in_record = False
                    records = pymarc.parse_xml_to_array(cStringIO.StringIO(buffer))
                    buffer = ""
                    for record in records:
                        record.__class__ = BRecord
                        yield record


if __name__=="__main__":
    all_hathi = All_Hathi()
    dump = gzip.open("/drobo/hathi_metafiles/jsoncatalog_full.txt.gz","w")
    for i,vol in enumerate(all_hathi):
        if i % 250000 == 0:
            sys.stdout.write("Reading item no. " + str(i) + "\n")
        dump.write(json.dumps(vol) + "\n")    
