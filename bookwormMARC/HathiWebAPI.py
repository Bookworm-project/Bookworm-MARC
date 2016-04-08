#! /usr/bin/python


"""
These functions are mostly useless since I switched to using DPLA instead of
Hathi as a metadata source
"""

def get_hathi_records(id):
    """
    Deprecated. Yields records from the Hathi web API. But I'm using
    """
    handler = XmlHandler()
    url = "http://catalog.hathitrust.org/api/volumes/full/json/htid:" +  id
    f = urllib2.urlopen(url)
    data = json.load(f)
    for record in hathi_xml_yielder(data):
        xml = cStringIO.StringIO(record.encode("utf-8"))
        parse_xml(xml,handler)
        for m in handler.records:
            yield m

def hathi_xml_yielder(data):
    """
    Yield records from the API. No longer necessary, now that I'm pulling from DPLA.
    """
    for key in data.keys():
        for record in data[key]['records']:
            yield data[key]['records'][record]['marc-xml']
