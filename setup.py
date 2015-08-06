import os.path
import setuptools

import pm

_APP_PATH = os.path.dirname(pm.__file__)

with open(os.path.join(_APP_PATH, 'resources', 'README.rst')) as f:
      long_description = f.read()

with open(os.path.join(_APP_PATH, 'resources', 'requirements.txt')) as f:
      install_requires = list(map(lambda s: s.strip(), f.readlines()))

setuptools.setup(
    name='path_manifest',
    version=pm.__version__,
    description="Inject a manifest of a directory structure and generate patches against it later.",
    long_description=long_description,
    classifiers=[],
    keywords='path manifest patch patches',
    author='Dustin Oprea',
    author_email='myselfasunder@gmail.com',
    url='https://github.com/dsoprea/PathManifest',
    license='GPL 2',
    packages=setuptools.find_packages(exclude=['dev']),
    include_package_data=True,
    zip_safe=False,
    package_data={
        'pm': [
            'resources/README.rst',
            'resources/requirements.txt'
        ],
    },
    install_requires=install_requires,
    scripts=[
          'pm/resources/scripts/pm_write_manifest',
          'pm/resources/scripts/pm_check_for_changes',
          'pm/resources/scripts/pm_make_differential_patch',
          'pm/resources/scripts/pm_show_applied_patches',
          'pm/resources/scripts/pm_read_patch_info',
    ],
)
