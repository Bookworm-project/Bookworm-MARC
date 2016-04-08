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


## How the code is organized.

The heart of the module is the new `BRecord` class in `bookwormMARC/bookwormMARC.py`.
This extends the existing `pymarc.Record` class with several new methods analogous to
the original `Record.title()` that just parses out the first title field.

Certain MARC fields, like 100 (creator) have so much useful information that rather than overload the main
class, I've created a few new classes (`Author` for field 100; `F008` for field 008) that can return a little dictionary
suitable for tacking onto the main record.

At a first pass, I'm opting to create methods for the *first* author, date, etc.; although MARC
allows for multiple fields in all of these, Bookworm queries frequently make more sense
with a single location. This will likely require some refactoring later.

## Hathi-MARC vs MARC in general

There are a number of particularities around Hathi MARC records that I (Ben) don't yet fully understand.
In particular, this relies a lot on the 974 field.

The files in bookwormMARC should be *generalizable* classes for reading in MARC records, although
they may have hathi-specific methods. I want this code to be portable to at least the Medical Heritage library.

Done right, this could be a quick and easy way to take any library catalog and build a Bookworm around at least
the metadata. That would be nice to have. 
