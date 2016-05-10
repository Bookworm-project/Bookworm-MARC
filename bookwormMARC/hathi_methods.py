import tarfile
import cStringIO
import random
import sys
import pymarc
from bookwormMARC import BRecord

def hathi_record_yielder(sample_files=100,sample_records=100):
    """
    Returns a generator that cycles, one at a time, through all the records.


    We're reading the full DPLA dump out of the tarfile, and then definnig a generator object from a yielding function.

    Each object returned by the generator is a record from the great pymarc utility.

    It has a native method for parsing multirecord marcxml, but that relies on reading the entire 
    giant files into the DOM. That's a waste of time, so I just chunk the records out by hand in a non-elegant way.
    This method may not work on non-Hathi MARC files if they use different patterns of newlines.
    """
    
    hathi_records = tarfile.open("dpla_full_20160501.tar.gz")    
    for file in hathi_records:
        if file.name.endswith(".xml") and random.random()<=(sample_files/float(100)):    
            sys.stderr.write("Parsing new XML file " + file.name)
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
