# What is new in demux 2.0

One section per new feature. The full list of changes is in `Changelog.md`; the install steps are in `docs/deployment/2.0/install.md`.

## End-to-end delivery

A finished MiSeq run is demultiplexed, QC'd, tarred, uploaded to IRIDA (VIGASP) and archived on NIRD, and every uploaded file is verified against its checksum, automatically.

## Oldest-first queue with a single lock

Pending runs are processed oldest first, one at a time. The lock is held from start to finish, so a second instance started during a run exits with `Demux already running, exiting.`

## A failed run stops the queue

A run that fails is marked with `DemultiplexFailed.txt` and is never retried. No newer run is started until the folders of the failed run are removed. Every 20 minutes the log repeats which run failed, why, the `rm` command that clears it and which runs are waiting behind it.

## Delivery columns in the SampleSheet

Four `[Data]` columns, filled by ShinyLIMS, decide where each sample goes: `Transfer_VIGAS`, `VIGASP_ID`, `Transfer_NIRD` and `NIRD_Location`. The sheet is validated before bcl2fastq starts; a wrong sheet stops the run with a message naming the column and the sample.

## Controls are kept out of delivery

Projects named `Control_<tag>` or `Negativ` are demultiplexed and kept in `/data/demultiplex/` but never QC'd, tarred or delivered. A project in which no sample produced reads is dropped with a warning instead of failing the run.

## IRIDA upload with checksum verification

For every sample with `Transfer_VIGAS=Yes` the FASTQ pair is uploaded into the project in `VIGASP_ID`, two pairs at a time, under one IRIDA sequencing run. Every uploaded file is checked against its checksum before the delivery is marked complete.

## NIRD archive in a flat layout

For every project with `Transfer_NIRD=Yes` the project tar file and its `.md5` and `.sha512` are copied into `<NIRD_Location>/` over SSH and the sums are recomputed on NIRD and compared. A tar file that already exists there stops the run; the script never overwrites a file on NIRD and never creates the target directory.

## SSH configuration comes from `~/.ssh/config`

Hostname, user, port, ProxyJump chain and host key checking for NIRD are read from the `seqtech` user's SSH config. The NIRD password and TOTP are fetched from the password manager at login time.

## Secrets in a password manager

No credential is in the code or in a config file. IRIDA and NIRD credentials are fetched from a password manager at the moment they are needed.

## Run state markers

The run folder gets a marker at the end of each phase:

- `DemultiplexComplete.txt`
- `VigaspDeliveryComplete.txt`
- `NirdDeliveryComplete.txt`
- `RunComplete.txt`

A run that stops gets `DemultiplexFailed.txt` instead, with the reason on the first line and the traceback below.

## demultiplex.py has subcommands now and the ability to skip parts

The arguments:

    <RunID> ...         process only these runs
    run <RunID> ...     synonym for the above
    --skip-vigasp       do not deliver to IRIDA
    --skip-nird         do not deliver to NIRD
    --version           print the version and exit
    --help              print the usage and exit

Pressing Tab completes subcommands, flags and RunIDs. Everything else in `--help` is planned. If not implemented, the script returns with `not yet implemented`.

## We can test now using semi-real data

There is no test instance of IRIDA on NREC and no test area on NIRD, so a full test has to upload to the production systems. `scripts/make_test_run.py <RunID>` clones a real run under the `999999_<instrument>_9999_` prefix with every sample renamed `TESTDATA_...`, so the real IRIDA projects and NIRD directories receive data that is unmistakably test data. `scripts/delete_test_pairs.py` removes the test pairs from IRIDA afterwards.

Example:

    scripts/make_test_run.py 260807_M09180_0070_000000000-MDJ2D

creates `/data/rawdata/999999_M09180_9999_000000003-MDJ2D`. This happens because `000000000`, `000000001` and `000000002` exist, which means that `000000003` is the next free counter. The timer picks it up like any other run.
