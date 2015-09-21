import logging
import os
import csv
import tempfile
import shutil
import json
import subprocess
import datetime
import pprint
import bz2
import fnmatch
import hashlib

import pm.config
import pm.config.patch
import pm.utility

_LOGGER = logging.getLogger(__name__)


class NoChangedFilesException(Exception):
    pass


class TooManyFilesException(Exception):
    pass


class Manifest(object):
    def __init__(self, root_path, manifest_filename=None, 
                 excluded_rel_paths=[], included_rel_paths=[],
                 excluded_rel_filepaths=[]):
        if os.path.exists(root_path) is False:
            raise ValueError("Root-path does not exist: [{0}]".\
                             format(root_path))

        manifest_filename = pm.config.patch.DEFAULT_MANIFEST_FILENAME

        self.__root_path = os.path.abspath(root_path)
        self.__manifest_filename = manifest_filename
        self.__excluded_rel_paths_s = set(excluded_rel_paths)
        self.__excluded_rel_filepaths_s = set(excluded_rel_filepaths)
        self.__included_rel_paths = included_rel_paths

    def file_gen(self):
        # Make sure all of the paths exist and that the excluded-paths are 
        # inside the root-path.

        prefix = self.__root_path + os.sep
        prefix_len = len(prefix)

        # Enumerate files.

        for (path, child_dirs, child_filenames) in os.walk(self.__root_path):
            skip_children = []
            do_process_files = True
            for child_dir in child_dirs:
                child_dir_path = os.path.join(path, child_dir)
                child_dir_rel_path = child_dir_path[prefix_len:]

                do_definite_include = False
                do_skip_path = False
                if self.__included_rel_paths:
                    _LOGGER.debug("We have one or more included-paths.")

# TODO(dustin): We should support patterns (fnmatch).
                    for included_rel_path in self.__included_rel_paths:
                        # The current child path matches an included path 
                        # exactly.
                        is_included = child_dir_rel_path.startswith(included_rel_path)
                        if is_included is True:
                            _LOGGER.debug("Including path: [%s]", included_rel_path)

                        # This current child path starts with an include path
                        # (include it).
                        child_starts_with_include_path = \
                            child_dir_rel_path.startswith(
                                included_rel_path + os.sep)

                        # This included path starts with the current child path
                        # (the included path is a descendant of the current
                        # directory).
                        included_path_starts_with_child = \
                            included_rel_path.startswith(
                                child_dir_rel_path + os.sep)

                        if is_included is True or \
                           child_starts_with_include_path is True or \
                           included_path_starts_with_child is True:
                            
                            if included_path_starts_with_child is True:
                                do_process_files = False

                            do_definite_include = True
                            break

                    # We were given a list of inclusions but the current 
                    # directory didn't qualify.
                    if do_definite_include is False:
                        do_skip_path = True

                # We either weren't given inclusions or the current directory 
                # matches an inclusion.
                if do_skip_path is False:
# TODO(dustin): We should support patterns (fnmatch).

# TODO(dustin): We mind want to revert to using lists if we're no longer 
#               benefiting from sets.
                    for exclude_rel_path in list(self.__excluded_rel_paths_s):
                        do_skip_path = child_dir_rel_path.startswith(exclude_rel_path)
                        if do_skip_path is True:
                            break

                    if do_skip_path is True:
                        _LOGGER.debug("Excluding path: [%s]", 
                                      child_dir_rel_path)

                        break

                # The current directory failed either the inclusions or the 
                # exclusions.
                if do_skip_path is True:
                    skip_children.append(child_dir)

            for skip_child in skip_children:
                child_dirs.remove(skip_child)

            if do_process_files is True:
                for child_filename in child_filenames:
                    # Skip anything that look like a patch-information file. 
                    # This is important so that subsequent patches don't pick-
                    # up the patch-file from earlier, applied patches.
                    if fnmatch.fnmatch(
                            child_filename, 
                            pm.config.patch.PATCH_INFO_FILENAME_PATTERN) is True:
                        continue

                    child_filepath = os.path.join(path, child_filename)
                    mtime_epoch = os.stat(child_filepath).st_mtime

                    rel_filepath = child_filepath[prefix_len:]

                    if rel_filepath == self.__manifest_filename:
                        _LOGGER.debug("Excluding manifest from file-list: [%s]",
                                      rel_filepath)

                        continue
# TODO(dustin): We should support patterns (fnmatch).
                    else:
# TODO(dustin): We mind want to revert to using lists if we're no longer 
#               benefiting from sets.
                        do_skip_file = False
                        for excluded_rel_filepath in list(self.__excluded_rel_filepaths_s):
                            do_skip_file = rel_filepath.startswith(excluded_rel_filepath)
                            if do_skip_file is True:
                                break

                        if do_skip_file is True:
                            _LOGGER.debug("Skipping excluded filepath: [%s]", 
                                          rel_filepath)

                            continue

                    yield (rel_filepath, int(mtime_epoch))

    def manifest_gen(self):
        manifest_filepath = \
            os.path.join(self.__root_path, self.__manifest_filename)

        # Force it to "write-text" (it defaults to binary despite the 
        # documentation).
        with bz2.BZ2File(manifest_filepath, 'r') as f:
            cr = csv.reader(f)
            for filepath, mtime_epoch_phrase in cr:
                yield filepath, int(mtime_epoch_phrase)

    def write_manifest(self, force=False):
        manifest_filepath = \
            os.path.join(self.__root_path, self.__manifest_filename)

        if os.path.exists(manifest_filepath) is True and force is False:
            raise EnvironmentError("Manifest already exists: [{0}]".\
                                   format(manifest_filepath))

        # Force it to "write-text" (it defaults to binary despite the 
        # documentation).
        with bz2.BZ2File(manifest_filepath, 'w') as f:
            cr = csv.writer(f)
            i = 0
            for filepath, mtime_epoch_phrase in self.file_gen():
                cr.writerow([filepath, str(mtime_epoch_phrase)])
                i += 1

        _LOGGER.debug("(%d) entries written.", i)

        return manifest_filepath

    def build_manifest_set(self):
        catalog_s = set()
        
        for (filepath, mtime_epoch) in self.manifest_gen():
            catalog_s.add((mtime_epoch, filepath))

        return catalog_s

    def compare(self):
        manifest_s = self.build_manifest_set()

        # Generate a list of files that we have that are new/changed from when 
        # the manifest was created.

        unknown = {}
        for entry in self.file_gen():
            (filepath, mtime_epoch) = entry
            item = (mtime_epoch, filepath)

            try:
                manifest_s.remove(item)
            except KeyError:
                unknown[filepath] = mtime_epoch

        removed = {}
        updated = {}

        for (mtime_epoch, filepath) in list(manifest_s):
            # The file has been changed since being recorded.
            if filepath in unknown:
                updated[filepath] = mtime_epoch
                del unknown[filepath]
            # The file has been removed since the manifest was created.
            else:
                removed[filepath] = mtime_epoch

        # All remaining files were added since the manifest was created.
        created = unknown

        if not created and not updated and not removed:
            raise NoChangedFilesException()

        return (created, updated, removed)

    def __inject_files_to_staging(self, rel_filepaths, temp_path):
        patch_files = {}
        for rel_filepath in rel_filepaths:
            from_filepath = os.path.join(self.__root_path, rel_filepath)
            to_filepath = os.path.join(temp_path, rel_filepath)

            _LOGGER.debug("Copying file to patch path: [%s] => [%s]", 
                          from_filepath, to_filepath)

            to_path = os.path.dirname(to_filepath)
            if os.path.exists(to_path) is False:
                os.makedirs(to_path)

            with open(from_filepath, 'rb') as f:
                with open(to_filepath, 'wb') as g:
                    shutil.copyfileobj(f, g)

            s = os.stat(from_filepath)
            mtime_epoch = int(s.st_mtime)
            filesize_b = s.st_size

            # Set patch mtime.
            os.utime(to_filepath, (mtime_epoch, mtime_epoch))

            hash_ = self.__get_md5_for_rel_filepath(rel_filepath)

            patch_files[rel_filepath] = {
                'mtime_epoch': mtime_epoch,
                'filesize_b': filesize_b,
                'hash_md5': hash_,
            }

        return patch_files

    def __write_patch_info(self, patch_name, patch_files_info, temp_path):
        now_phrase = \
            datetime.datetime.now().strftime(
                pm.config.patch.TIMESTAMP_FORMAT)

        patch_info = {
            'patch_name': patch_name,
            'created_timestamp': now_phrase,
            'files': patch_files_info,
        }

        # Deposit a patch-info file.

        replacements = {
            'name': patch_name,
        }

        patch_info_filename = \
            pm.config.patch.PATCH_INFO_FILENAME_TEMPLATE % replacements

        patch_info_filepath = \
            os.path.join(temp_path, patch_info_filename)

        with open(patch_info_filepath, 'w') as f:
            pm.utility.pretty_json_dump(patch_info, f)

        return (patch_info_filename, patch_info)

    def __build_archive(self, patch_name, patch_output_path, temp_path, 
                        rel_filepaths):
        # Build the archive.

        replacements = {
            'name': patch_name,
        }

        patch_filename = \
            pm.config.patch.PATCH_FILENAME_TEMPLATE % replacements

        patch_filepath = os.path.join(patch_output_path, patch_filename)

        current_wd = os.getcwd()

        try:
            os.chdir(temp_path)

            cmd = [
                'tar', 
                'cjf', patch_filepath, 
                '-T', '-',
            ]

            _LOGGER.debug("Building archive: [%s]", cmd)

            p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            p.communicate('\n'.join(rel_filepaths))
            if p.returncode != 0:
                raise ValueError("Archive failed.")
        finally:
            os.chdir(current_wd)

        return patch_filepath

    def make_patch(self, patch_name, patch_output_path, max_files=None):
        temp_path = tempfile.mkdtemp()
        _LOGGER.debug("Path temporary path: [%s]", temp_path)

        result = self.compare()
        (created, updated, removed) = result

        changed_rel_filepaths = sorted(list(created.keys()) + list(updated.keys()))

        if not changed_rel_filepaths:
            raise NoChangedFilesException()

        if pm.config.IS_DEBUG is True:
            _LOGGER.debug("Files to capture in the patch:\n%s", 
                          pprint.pformat(changed_rel_filepaths))

        patch_files_info = \
            self.__inject_files_to_staging(changed_rel_filepaths, temp_path)

        if max_files is not None:
            len_ = len(patch_files_info)
            if len_ > max_files:
                rel_filepaths = sorted(patch_files_info.keys())
                _LOGGER.error("Too many files will be included in the patch:\n"
                              "%s", 
                              pm.utility.pretty_json_dumps(rel_filepaths))

                raise TooManyFilesException("Too many files ({0}) are in the "
                                            "patch. Either make sure you're "
                                            "excluding/including correctly "
                                            "or adjust the limit.".\
                                            format(len_))

        (patch_info_filename, patch_info) = \
            self.__write_patch_info(patch_name, patch_files_info, temp_path)

        files_to_include = [patch_info_filename] + patch_files_info.keys()

        try:
            patch_filepath = \
                self.__build_archive(
                    patch_name, 
                    patch_output_path, 
                    temp_path, 
                    files_to_include)
        finally:
            if pm.config.IS_DEBUG is False:
                shutil.rmtree(temp_path)
            else:
                _LOGGER.warning("Not removing temp-path since we're running "
                                "in debug-mode: [%s]", temp_path)

        return (patch_filepath, patch_info)

    def __get_md5_for_rel_filepath(self, rel_filepath):
        h = hashlib.md5()
        chunk_size_b = 128
        
        filepath = os.path.join(self.__root_path, rel_filepath)
        with open(filepath, 'rb') as f:
            while 1:
                chunk = f.read(chunk_size_b)
                h.update(chunk)

                if len(chunk) < chunk_size_b:
                    break

        return h.hexdigest()

    def get_hashes_for_files_in_patch(self, patch_info):
        hashes = {}
        for rel_filepath in patch_info['files'].keys():
            hash_ = self.__get_md5_for_rel_filepath(rel_filepath)
            hashes[rel_filepath] = hash_

        return hashes

    def get_applied_patches(self):
        patches = []
        affected_rel_filepaths_s = set()
        for filename in os.listdir(self.__root_path):
            if fnmatch.fnmatch(
                    filename, 
                    pm.config.patch.PATCH_INFO_FILENAME_PATTERN) is False:
                continue

            filepath = os.path.join(self.__root_path, filename)

            with open(filepath) as f:
                patch_info = json.load(f)
                patches.append(patch_info)

                rel_filepaths = patch_info['files'].keys()
                affected_rel_filepaths_s.update(set(rel_filepaths))

        return (patches, list(affected_rel_filepaths_s))

    def __get_rel_filepaths_in_tarbz2(self, filepath, pattern):
        cmd = [
            'tar', 
            'tjf', filepath, 
        ]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        filelist_raw = p.stdout.read()
        if p.wait() != 0:
            raise ValueError("Could not read file: [{0}]".format(filepath))

        for rel_filepath in filelist_raw.split('\n'):
            filename = os.path.basename(rel_filepath)
            if fnmatch.fnmatch(filename, pattern) is True:
                yield rel_filepath

    def __read_rel_filepath_from_tarbz2(self, filepath, entry_rel_filepath):
        cmd = [
            'tar', 
            'xjOf', filepath, 
            entry_rel_filepath,
        ]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        data = p.stdout.read()
        if p.wait() != 0:
            raise ValueError("Could not read entry [{0}] from tar.bz2: [{1}]".\
                             format(rel_filepath, patch_filepath))

        return data

    def get_raw_patch_info_from_file(self, patch_filepath):
        rel_filepaths = \
            self.__get_rel_filepaths_in_tarbz2(
                patch_filepath, 
                pm.config.patch.PATCH_INFO_FILENAME_PATTERN)

        rel_filepaths = list(rel_filepaths)
        assert \
            len(rel_filepaths) == 1, \
            "We needed to find exactly one patch-file: {0}".\
            format(rel_filepaths)

        rel_filepath = rel_filepaths[0]

        patch_info = \
            self.__read_rel_filepath_from_tarbz2(patch_filepath, rel_filepath)

        return patch_info
