#!/usr/bin/env python3

import sys
import os
import re
import requests
import json

INDEX_NODES = (
    "esgf-node.llnl.gov",
    "esgf-data.dkrz.de",
    "esgf.nci.org.au",
    "esg-dn1.nsc.liu.se",
    "esgf-index1.ceda.ac.uk",
    "esgf-node.ipsl.upmc.fr",
)

def help():
    print("""  esgfsearch [--local] [--stop N]
    [--format (json|csv|aria2c|meta4|meta4f)]
    [--filter (cmip6|cordex|cmip5|FACETS)           FACETS are facets separated by ",".
    [-q QUERY]...                                   QUERY in "facet1=value1 facet2=value2,value3" format.
    SELECTIONS...""", file=sys.stderr)

def parse_arguments(argv):
    args = {
        "filter": None,
        "format": "json",
        "from": None,
        "local": False,
        "query": [],
        "selections": [],
        "stop": None,
    }

    position = 1
    arguments = len(argv) - 1
    if arguments < 1:
        help()
        sys.exit(1)

    while arguments >= position:
        if argv[position] == "-h" or argv[position] == "--help":
            help()
            sys.exit(1)
        elif argv[position] == "--filter":
            args["filter"] = argv[position+1]
            position+=2
        elif argv[position] == "--from":
            args["from"] = argv[position+1]
            position+=2
        elif argv[position] == "--format" or argv[position] == "-f":
            args["format"] = argv[position+1]
            position+=2
        elif argv[position] == "--local":
            args["local"] = True
            position+=1
        elif argv[position] == "--query" or argv[position] == "-q":
            args["query"].append(argv[position+1])
            position+=2
        elif argv[position] == "--stop":
            args["stop"] = int(argv[position+1])
            position+=2
        else:
            args["selections"].append(argv[position])
            position+=1

    return args

def parse_selection(sfile):
    query = {}
    with open(sfile, "r") as f:
        for line in f:
            if line == "\n" and query:
                yield query
                query = {}
            elif line != "\n":
                params = line.rstrip("\n").split()
                for param in params:
                    k = param.split("=")[0]
                    v = param.split("=")[1]
                    query[k] = v

        if query:
            yield query

def parse_query(query):
    queryd = {}
    params = query.replace("\n", " ").split()
    for param in params:
        k = param.split("=")[0]
        v = param.split("=")[1]
        queryd[k] = v

    return queryd

def range_search(endpoint, session, query, stop=None):
    payload = query.copy()

    # how many records?
    payload["limit"] = 0
    payload["format"] = "application/solr+json"
    r = session.get(endpoint, params=payload, timeout=120)
    print("Query results for {}".format(r.url), file=sys.stderr)
    n = r.json()["response"]["numFound"]
    print("Found {} for {}".format(n, r.url), file=sys.stderr)

    # if stop < n, restrict
    if stop is not None and stop < n:
        n = stop

    # small optimization
    limit = 9000 # theoretically it is 10_000 but sometimes it fails
    if n < limit:
        limit = n

    # clean payload and start searching
    payload = query.copy()
    i = 0
    while i < n:
        payload["limit"] = limit
        payload["format"] = "application/solr+json"
        payload["offset"] = i

        r = session.get(endpoint, params=payload, timeout=120)
        print(r.url, file=sys.stderr)
        docs = r.json()["response"]["docs"]
        for f in docs:
            i += 1
            yield f

            if i >= n:
                break

def standard_search(query, stop):
    s = requests.Session()
    endpoint = "https://{}/esg-search/search".format(INDEX_NODES[0])
    for result in range_search(endpoint, s, query, stop):
        yield result
    s.close()

def nondistrib_search(query, stop):
    for index_node in INDEX_NODES:
        s = requests.Session()
        params = query.copy()
        params["distrib"] = "false"
        endpoint = "https://{}/esg-search/search".format(index_node)

        for result in range_search(endpoint, s, params, stop):
            yield result

        s.close()

class Formatter():
    def dump(self, item):
        print(json.dumps(item))

    def terminate(self):
        pass

class CsvFormatter(Formatter):
    def __init__(self):
        self.columns = None

    def dump(self, item):
        if self.columns is None:
            self.set_columns_from_item(item)
            # first line of the csv will be the headers
            columns = ["\"" + c + "\"" for c in self.columns]
            print(",".join(columns))

        values = {}
        for c in self.columns:
            values[c] = "\"\""
            if c not in item:
                continue
            elif isinstance(item[c], list) and "project" in item and item["project"][0].lower() == "cmip5":
                values[c] = self.csv_value(",".join(item[c]))
            elif isinstance(item[c], list):
                values[c] = self.csv_value(item[c][0])
            else:
                values[c] = self.csv_value(str(item[c]))

        if "url" in item:
            urls = item["url"]
            for url in urls:
                parts = url.split("|")
                endpoint = parts[0]
                endpoint_type = parts[-1]
                values[endpoint_type] = self.csv_value(endpoint)

        row = ",".join([values[column] for column in self.columns])
        print(row)

    def set_columns_from_item(self, item):
        self.columns = ["HTTPServer", "GridFTP", "OPENDAP"]
        for k in item:
            if k not in self.columns:
                self.columns.append(k)

    def csv_value(self, value):
        return "\"" + value.replace("\"", "") + "\""

class Aria2cFormatter(Formatter):
    def __init__(self):
        self.store = {}

    def dump(self, item):
        title = item["title"]
        title = re.sub("\.nc_[0-9]+$", ".nc", title)
        title = re.sub("\.nc[0-9]+$", ".nc", title)
        instance_id = item["instance_id"]
        instance_id = re.sub("\.nc_[0-9]+$", ".nc", instance_id)
        instance_id = re.sub("\.nc[0-9]+$", ".nc", instance_id)
        if not title in instance_id:
            instance_id = ".".join([instance_id, title])

        # fuck cordex
        if instance_id.split(".")[0].lower() == "cordex":
            parts = instance_id.split(".")
            parts[7] = "-".join([parts[3], parts[7]])
            instance_id = ".".join(parts)

        urls = filter(lambda x: x.endswith("HTTPServer"), item["url"])
        urls = [url.split("|")[0] for url in urls]

        checksum = item["checksum"][0]
        checksum_type = item["checksum_type"][0].replace("SHA", "sha-").replace("MD5", "md5")

        if instance_id in self.store:
            self.store[instance_id]["urls"].extend(urls)
        else:
            self.store[instance_id] = {
                "urls": urls,
                "checksum": checksum,
                "checksum_type": checksum_type,
                "out": instance_id.rstrip(".nc").replace(".", "/") + ".nc"
            }

    def terminate(self):
        for instance_id in self.store:
            print("\t".join(self.store[instance_id]["urls"]))
            print("  checksum={}={}".format(
                self.store[instance_id]["checksum_type"],
                self.store[instance_id]["checksum"]))
            print("  out={}".format(self.store[instance_id]["out"]))

class Metalink4Formatter(Aria2cFormatter):
    def __init__(self):
        self.store = {}

    def terminate(self):
        print('<?xml version="1.0" encoding="UTF-8"?>')
        print('<metalink xmlns="urn:ietf:params:xml:ns:metalink">')
        for instance_id in self.store:
            print('  <file name="{}">'.format(self.store[instance_id]["out"]))
            print('    <hash type="{}">{}</hash>'.format(
                self.store[instance_id]["checksum_type"],
                self.store[instance_id]["checksum"]))
            for url in self.store[instance_id]["urls"]:
                print('    <url priority="1">{}</url>'.format(url))
            print('  </file>')
        print('</metalink>')

class Metalink4fFormatter(Aria2cFormatter):
    def __init__(self):
        self.store = {}

    def terminate(self):
        print('<?xml version="1.0" encoding="UTF-8"?>')
        print('<metalink xmlns="urn:ietf:params:xml:ns:metalink">')
        for instance_id in self.store:
            basename = self.store[instance_id]["out"].split("/")[-1]
            print('  <file name="{}">'.format(basename))
            print('    <hash type="{}">{}</hash>'.format(
                self.store[instance_id]["checksum_type"],
                self.store[instance_id]["checksum"]))
            for url in self.store[instance_id]["urls"]:
                print('    <url priority="1">{}</url>'.format(url))
            print('  </file>')
        print('</metalink>')

class Filter():
    def __init__(self):
        self.facets = []

    def filter(self, item):
        return item

class FacetFilter(Filter):
    def __init__(self, facets):
        self.facets = facets

    def filter(self, item):
        return {k: item[k] for k in self.facets}

class Cmip6Filter(FacetFilter):
    def __init__(self):
        self.facets = [
            "project", "activity_id", "source_id", "institution_id", "experiment_id",
            "member_id", "table_id", "variable_id", "grid_label", "frequency", "realm",
            "size", "version", "title"
        ]

class CordexFilter(FacetFilter):
    def __init__(self):
        # "product" is excluded because it doesn't exist sometimes
        self.facets = [
            "project", "domain", "driving_model", "experiment", "time_frequency",
            "ensemble", "variable", "rcm_name", "rcm_version", "version", "size",
            "title"
        ]

class Cmip5Filter(FacetFilter):
    def __init__(self):
        self.facets = [
            "project", "product", "model", "experiment", "time_frequency", "cmor_table",
            "variable", "ensemble", "size", "version", "title"
        ]

if __name__ == "__main__":
    args = parse_arguments(sys.argv)

    if args["format"] == "json":
        formatter = Formatter()
    elif args["format"] == "csv":
        formatter = CsvFormatter()
    elif args["format"] == "aria2c":
        formatter = Aria2cFormatter()
    elif args["format"] == "meta4":
        formatter = Metalink4Formatter()
    elif args["format"] == "meta4f":
        formatter = Metalink4fFormatter()
    else:
        print("Error: Unknown format '{}', exiting...".format(args["format"]), file=sys.stderr)
        sys.exit(1)

    if args["filter"] is None:
        filt = Filter()
    elif args["filter"] == "cmip6":
        filt = Cmip6Filter()
    elif args["filter"] == "cordex":
        filt = CordexFilter()
    elif args["filter"] == "cmip5":
        filt = Cmip5Filter()
    else: # if not recognized, use facets separated by ,
        facets = args["filter"].split(",")
        filt = FacetFilter(facets)

    # just convert and exit
    if args["from"] is not None:
        with open(args["from"], "r") as f:
            for result in f:
                formatter.dump(filt.filter(json.loads(result)))
        # for formatters that store in memory
        formatter.terminate()
        sys.exit(0)

    # search query
    for query in args["query"]:
        if args["local"]:
            for result in nondistrib_search(parse_query(query), args["stop"]):
                formatter.dump(filt.filter(result))
        else:
            for result in standard_search(parse_query(query), args["stop"]):
                formatter.dump(filt.filter(result))

    # search selections
    for selection in args["selections"]:
        for query in parse_selection(selection):
            if args["local"]:
                for result in nondistrib_search(query, args["stop"]):
                    formatter.dump(filt.filter(result))
            else:
                for result in standard_search(query, args["stop"]):
                    formatter.dump(filt.filter(result))

    # for formatters that store in memory
    formatter.terminate()
