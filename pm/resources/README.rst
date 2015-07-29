------------
Introduction
------------

This project allows you to fingerprint a directory by dropping a manifest of relative filepaths and modified-times into it, and then build patches against it later and maintain a history of patching. Inclusions and exclusions can be specified and most of the commands can output JSON-encoded data so that they can be internalized from other tools.

To apply a patch, merely expand it in the directory. Obviously we don't manage files that have been removed.


-----
Tools
-----

pm_write_manifest
=================

Write a manifest of the complete contents of a given directory to the root of the same directory. The path can be absolute or relative.

Command-Line Help::

    usage: pm_write_manifest [-h] [-f] [-mf MANIFEST_FILENAME] [-e REL-PATH]
                             [-ef REL-FILEPATH] [-i REL-PATH] [-j]
                             root_path

    Write file-manifest for the contents of the given path.

    positional arguments:
      root_path             Root path

    optional arguments:
      -h, --help            show this help message and exit
      -f, --force           Force the replacement of an existing manifest
      -mf MANIFEST_FILENAME, --manifest-filename MANIFEST_FILENAME
                            Manifest filename
      -e REL-PATH, --exclude-rel-path REL-PATH
                            Ignore the contents of this child path
      -ef REL-FILEPATH, --exclude-rel-filepath REL-FILEPATH
                            Ignore this filepath
      -i REL-PATH, --include-rel-path REL-PATH
                            Constraint the matched files to one or more
                            directories
      -j, --json            Print result in JSON

Usage::

    $ pm_write_manifest /application/root


pm_check_for_changes
====================

Print a list of the changes since the manifest was written.

Command-Line Help::

    usage: pm_check_for_changes [-h] [-mf MANIFEST_FILENAME] [-e REL-PATH]
                                [-ef REL-FILEPATH] [-i REL-PATH] [-ir]
                                root_path

    Check the given path for changes since the manifest was written.

    positional arguments:
      root_path             Root path

    optional arguments:
      -h, --help            show this help message and exit
      -mf MANIFEST_FILENAME, --manifest-filename MANIFEST_FILENAME
                            Manifest filename
      -e REL-PATH, --exclude-rel-path REL-PATH
                            Ignore the contents of this child path
      -ef REL-FILEPATH, --exclude-rel-filepath REL-FILEPATH
                            Ignore this filepath
      -i REL-PATH, --include-rel-path REL-PATH
                            Constraint the matched files to one or more
                            directories
      -ir, --ignore-removed
                            Do not show removed files (helpful when we include
                            specific subdirectories)

Usage::

    $ pm_check_for_changes /application/root
    New
    ---
    new_directory/new_file2
    new_file

    Updated
    -------
    updated_file


pm_make_differential_patch
==========================

Build a new patch with the difference between the current directory and the state when the manifest was written.

Command-Line Help::

    usage: pm_make_differential_patch [-h] [-mf MANIFEST_FILENAME] [-e REL-PATH]
                                      [-i REL-PATH] [-ef REL-FILEPATH] [-j]
                                      [-m COUNT]
                                      root_path patch_name output_path

    Create an archive with all differences since the manifest was written.

    positional arguments:
      root_path             Root path
      patch_name            Patch name
      output_path           Output path

    optional arguments:
      -h, --help            show this help message and exit
      -mf MANIFEST_FILENAME, --manifest-filename MANIFEST_FILENAME
                            Manifest filename
      -e REL-PATH, --exclude-rel-path REL-PATH
                            Ignore the contents of this child path
      -i REL-PATH, --include-rel-path REL-PATH
                            Constraint the matched files to one or more
                            directories
      -ef REL-FILEPATH, --exclude-rel-filepath REL-FILEPATH
                            Ignore this filepath
      -j, --json            Print result in JSON
      -m COUNT, --max-files COUNT
                            A safe maximum for the number of allowed files in the
                            patch (0 for unlimited)

Usage::

    $ pm_make_differential_patch /application/root 201507282031 /tmp
    Created/Updated Files
    ---------------------

    new_directory/new_file2
    updated_file
    new_file

    Patch file-path:

    /tmp/pm-patch-201507282031.tar.bz2


pm_show_applied_patches
=======================

Command-Line Help::

    usage: pm_show_applied_patches [-h] [-j] root_path

    Show the patches that have been applied to the application.

    positional arguments:
      root_path   Root path

    optional arguments:
      -h, --help  show this help message and exit
      -j, --json  Print result in JSON

Usage::

    $ pm_show_applied_patches /application/root
    Applied Patches
    ---------------

    201507282031

    Affected Files
    --------------

    new_directory/new_file2
    updated_file
    new_file

Notes
-----

This is merely a tool of convenience. All patches will deposit a file that looks like ".patch_info.XYZ" into the application root. For example, the patch that we created above deposited a file named ".patch_info.201507282031". This holds JSON-encoded data that describes the patch.

Example::

    $ cat .patch_info.201507282031 
    {
        "created_timestamp": "2015-07-28 20:31:28",
        "files": {
            "new_directory/new_file2": {
                "filesize_b": 0,
                "mtime_epoch": 1438129768
            },
            "new_file": {
                "filesize_b": 0,
                "mtime_epoch": 1438129731
            },
            "updated_file": {
                "filesize_b": 0,
                "mtime_epoch": 1438129728
            }
        },
        "patch_name": "201507282031"
    }

    Note that the filesizes were zero merely because we created empty-files for the purpose of these examples.


-------------------------
Patch Application Example
-------------------------

Once you have a patch, simply expand it into the application root in order to apply it::

    $ tar xjf /tmp/pm-patch-201507282031.tar.bz2 
