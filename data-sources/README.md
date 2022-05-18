# Data sources

The following information contains instructions to replicate the datasets from ESGF used in the paper. This directory contains:

- `datasets` - NcML datasets used as input in the notebook.
- `datasets.meta4` - Metalink file that downloads data sources from ESGF.
- `selection` - [Synda](https://prodiguer.github.io/synda/index.html) like selection file used to retrieve data sources from ESGF, in order to create the `datasets.meta4` file.
- `esgfsearch.py` - Python script that generates `datasets.meta4` from `selection`, by quering ESGF.

Use any Metalink compatible client to download the datasets from ESGF using the `datasets.meta4` file. Note that both CMIP5 and CORDEX are restricted and require a free account in the ESGF.

The selection file was generated using:

```bash
find datasets/ -type f | while read f
do
    awk -F'"' '
/location="/
{
    sub(".*/", "", $2)
    printf("type=File latest=true title=%s\n\n", $2)
}' ${f} ; done > selection
```

To generate `datasets.meta4`:

```bash
./esgfsearch.py --format meta4 selection > datasets.meta4
```

You may download the datasets using [aria2c](https://aria2.github.io/) along with [MyProxyClient](https://pypi.org/project/MyProxyClient/) to obtain a ESGF credential:

```bash
myproxyclient logon -s ${INDEX} -l ${USER} -b -o certificate.pem  -p 7512 -t720
aria2c --private-key=certificate.pem \
           --certificate=certificate.pem \
           --ca-certificate=certificate.pem \
           --check-certificate=false \
           --log-level=info --summary-interval=0 --console-log-level=warn \
           --allow-overwrite=true --continue --file-allocation=none --remote-time=true \
           --auto-file-renaming=false --conditional-get=true --check-integrity=true \
           datasets.meta4
```
