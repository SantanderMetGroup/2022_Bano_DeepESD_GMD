# Data sources

The following information contains instructions to replicate the datasets from ESGF used in the paper. This directory contains:

- `datasets` - NcML datasets used as input in the notebook.
- `datasets.meta4` - Metalink file that downloads data sources from ESGF.
- `selection` - [Synda](https://prodiguer.github.io/synda/index.html) like selection file used to retrieve data sources from ESGF, in order to create the `datasets.meta4` file.
- `esgfsearch.py` - Python script that generates `datasets.meta4` from `selection`, by quering ESGF.

Use any Metalink compatible client to download the datasets from ESGF using the `datasets.meta4` file. Note that both CMIP5 and CORDEX are restricted and require a free account in the ESGF. Also, you may prefer to use [Synda](https://prodiguer.github.io/synda/index.html) together with the selection file in order to perform the download.
