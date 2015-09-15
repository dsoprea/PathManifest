import os

TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'
PATCH_FILENAME_TEMPLATE = 'pm-patch-%(name)s.tar.bz2'
PATCH_INFO_FILENAME_TEMPLATE = '.patch_info.%(name)s'
PATCH_INFO_FILENAME_PATTERN = '.patch_info.*'

DEFAULT_MANIFEST_FILENAME = '.manifest.csv.bz2'
NAME_RX = r"^[a-zA-Z0-9_\-]+$"
DEFAULT_MAXIMUM_ALLOWED_FILES_IN_PATCH = \
    int(os.environ.get('PM_MAXIMUM_ALLOWED_FILES_IN_PATCH', '50'))
