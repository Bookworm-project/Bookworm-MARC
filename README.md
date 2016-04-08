# MARC parsing into Bookworm

This repo should build metadata for a HathiTrust bookworm from original MARC records.
It builds off of the pymarc module to pull metadata likely to be useful in analysis.
This includes:

1. Dates
2. Author information
3. Classification information
4. Titles
5. Language information
6. Holding library information
7. Scanner information.

There are a number of particularities around Hathi MARC records that I (Ben) don't yet fully understand.
In particular, this relies a lot on the 974 field.

The files in bookwormMARC should be *generalizable* classes for reading in MARC records, although
they may have hathi-specific methods. I want this code to be portable to at least the Medical Heritage library.

Done right, this could be a quick and easy way to take any library catalog and build a Bookworm around at least
the metadata. That would be nice to have. 
