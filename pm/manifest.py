import logging
import os
import csv
import tempfile
import shutil
import json
import subprocess
import datetime
import pprint

import pm.config
import pm.config.patch
import pm.utility

_LOGGER = logging.getLogger(__name__)


class NoChangedFilesException(Exception):
    pass


class Manifest(object):
    def __init__(self, root_path, manifest_filename=None, 
                 excluded_rel_paths=[]):
        if os.path.exists(root_path) is False:
            raise ValueError("Root-path does not exist: [{0}]".\
                             format(root_rel_path))

        manifest_filename = pm.config.patch.DEFAULT_MANIFEST_FILENAME

        self.__root_path = os.path.abspath(root_path)
        self.__manifest_filename = manifest_filename
        self.__excluded_rel_paths = excluded_rel_paths

    def file_gen(self):
        # Make sure all of the paths exist and that the excluded-paths are 
        # inside the root-path.

        prefix = self.__root_path + os.sep
        prefix_len = len(prefix)

        # Enumerate files.

        for (path, child_dirs, child_filenames) in os.walk(self.__root_path):
            skip_children = []
            for child_dir in child_dirs:
                child_dir_filepath = os.path.join(path, child_dir)
                child_dir_rel_filepath = child_dir_filepath[prefix_len:]

                do_skip = False
                for excluded_rel_path in self.__excluded_rel_paths:
                    if child_dir_rel_filepath.startswith(excluded_rel_path):
                        do_skip = True
                        break

                if do_skip is True:
                    skip_children.append(child_dir)

            for skip_child in skip_children:
                child_dirs.remove(skip_child)

            for child_filename in child_filenames:
                child_filepath = os.path.join(path, child_filename)
                mtime_epoch = os.stat(child_filepath).st_mtime

                rel_filepath = child_filepath[prefix_len:]

                if rel_filepath == self.__manifest_filename:
                    _LOGGER.debug("Excluding manifest from file-list: [{0}]".\
                                  format(rel_filepath))

                    continue

                yield (rel_filepath, int(mtime_epoch))

    def manifest_gen(self):
        manifest_filepath = \
            os.path.join(self.__root_path, self.__manifest_filename)

        with open(manifest_filepath) as f:
            cr = csv.reader(f)
            for filepath, mtime_epoch_phrase in cr:
                yield filepath, int(mtime_epoch_phrase)

    def write_manifest(self):
        manifest_filepath = \
            os.path.join(self.__root_path, self.__manifest_filename)

        with open(manifest_filepath, 'w') as f:
            cr = csv.writer(f)
            for filepath, mtime_epoch_phrase in self.file_gen():
                cr.writerow([filepath, str(mtime_epoch_phrase)])

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

            patch_files[rel_filepath] = {
                'mtime_epoch': mtime_epoch,
                'filesize_b': filesize_b,
            }

        return patch_files

    def __write_patch_info(self, patch_name, patch_files, temp_path):
        now_phrase = \
            datetime.datetime.now().strftime(
                pm.config.patch.TIMESTAMP_FORMAT)

        patch_info = {
            'patch_name': patch_name,
            'created_timestamp': now_phrase,
            'files': patch_files,
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

    def __build_archive(self, patch_name, patch_output_path, temp_path):
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

            cmd = ['tar', 'cjf', patch_filepath, '.']
            _LOGGER.debug("Building archive: [%s]", cmd)

            p = subprocess.Popen(cmd)
            if p.wait() != 0:
                raise ValueError("Archive failed.")
        finally:
            os.chdir(current_wd)

        return patch_filepath

    def make_patch(self, patch_name, patch_output_path):
        temp_path = tempfile.mkdtemp()
        _LOGGER.debug("Path temporary path: [%s]", temp_path)

        result = self.compare()
        (created, updated, removed) = result

        changed_rel_filepaths = list(created.keys()) + list(updated.keys())

        if not changed_rel_filepaths:
            raise NoChangedFilesException()

        if pm.config.IS_DEBUG is True:
            _LOGGER.debug("Files to capture in the patch:\n%s", 
                          pprint.pformat(changed_rel_filepaths))

        patch_files = \
            self.__inject_files_to_staging(changed_rel_filepaths, temp_path)

        self.__write_patch_info(patch_name, patch_files, temp_path)

        try:
            patch_filepath = \
                self.__build_archive(patch_name, patch_output_path, temp_path)
        finally:
            if pm.config.IS_DEBUG is False:
                shutil.rmtree(temp_path)
            else:
                _LOGGER.warning("Not removing temp-path since we're running "
                                "in debug-mode: [%s]", temp_path)

        return patch_filepath
