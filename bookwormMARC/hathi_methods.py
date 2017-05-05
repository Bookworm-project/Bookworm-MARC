import tarfile
import cStringIO
import random
import sys
import pymarc
from bookwormMARC import BRecord
from bookwormMARC import LCCallNumber
import logging
import ujson as json
import multiprocessing
from multiprocessing import Process, Queue, Pool
import multiprocessing as mp
import bz2
import Queue
import glob

"""
These define methods specific to Hathi Trust MARC record parser.
"""



                
def hathi_item_yielder():
    records = hathi_record_yielder()
    for record in records:
        for item in record.hathi_bookworm_dicts():
            yield item

def obj_to_marc(line):
    """
    Converts a python dictionary object into a MARC record.
    For when the data comes as JSON.
    """
    jobj = json.loads(line)    
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

def hathi_yielder(root,n_threads,mod,queue=None, full_lcc = False, base_record = False):
    
    if not root.endswith("/"):
        # I always forget to end dirs with a slash.
        root = root + "/"

    # These are the four files Hathi gave me.
    base_names = ["meta_pd_google.json.bz2","meta_ic.json.bz2",
                  "meta_pd_open_access.json.bz2","meta_restricted.json.bz2"]

    # Ensures that the threads will have a different order which means
    # a random sample will draw from different files.
    # Just a little useful.
    random.shuffle(base_names)
    
    for name in base_names:
        file = bz2.BZ2File(root + name)
        for i,line in enumerate(file):
            # i is defined for this thread.
            # This
            # enables parallelism.
            if i % n_threads == mod:
                record = obj_to_marc(line)
                vols = record.hathi_bookworm_dicts()
                lcc = False
                if full_lcc:
                    try:
                        lcc = LCCallNumber(record["050"].value())
                    except:
                        pass
                if base_record:
                    queue.put(record)
                else:
                    for vol in vols:
                        if lcc:
                            vol["lcc"] = lcc
                        queue.put(vol)

def loc_yielder(root,n_threads,mod,queue=None, full_lcc = False, base_record = False):
    if not root.endswith("/"):
        # I always forget to end dirs with a slash.
        root = root + "/"


    # These are the four files Hathi gave me.
    base_names = glob.glob(root + "*.utf8")
    # Scrimp down to just a few of the files for this specific thread.
    base_names = [name for name in base_names if ((hash(name) % n_threads) == mod)]

    # Ensures that the threads will have a different order which means
    # a random sample will draw from different files.
    # Just a little useful.
    random.shuffle(base_names)

    for name in base_names:
        print name
        reader = pymarc.MARCReader(open(name))
        for record in reader:
            record.__class__ = BRecord
            dicto = record.bookworm_dict()
            if full_lcc:
                try:
                    dicto["lcc"] = LCCallNumber(record["050"].value())
                except:
                    pass
            queue.put(dicto)

class All_Hathi(object):
    """
    An iterable for Hathi books. Casually multithreaded.

    full_lcc: return a full class for the lcc classification, not just the headline numbers

    base_record: return not a bookworm_dict, but the underlying MARC record.
    """
    def __init__(self,root="/drobo/hathi_metafiles", n_threads=4, full_lcc=False, base_record = False, cat = "hathi"):
        self.root = root
        # Only let it get so long, just in case.
        self.q = mp.Queue(100)
        self.processes = []
        self.n_threads = n_threads
        for i in range(n_threads):
            if cat == "hathi":
                p2 = mp.Process(target=hathi_yielder,args=(root, n_threads, i, self.q, full_lcc, base_record))
            elif cat == "LOC":
                p2 = mp.Process(target=loc_yielder,args=(root, n_threads, i, self.q, full_lcc, base_record))
            else:
                raise TypeError("No method defined for {}".format(cat))

            self.processes.append(p2)

        for p in self.processes:
            p.start()
            
    def __iter__(self):
        import time
        while True:
            try:
                # It should never take a full second to do this.
                yield self.q.get(timeout=1)
            except Queue.Empty:
                all_empty = True
                for p in self.processes:
                    if p.is_alive():
                        all_empty = False
                    else:
                        print "dead process"
                if all_empty:
                    for p in self.processes:
                        # kill?
                        pass
                    break
                else:
                    continue
                    
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
            for line in open(file,"r"):
                #hathi_records.extractfile(file):\

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
    pass
