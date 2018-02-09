from os import path
from setuptools import setup

tests_require = ['pytest']

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='consulk8s',
    use_scm_version=True,
    py_modules=['consulk8s'],
    license='BSD',
    author='Josh Benner',
    author_email='joshb@aweber.com',
    url='https://github.com/joshbenner/consulk8s',
    description='Integrate Consul and Kubernetes',
    long_description=long_description,
    setup_requires=['setuptools_scm'],
    tests_require=tests_require,
    extras_require={
        'test': tests_require
    },
    install_requires=[
        'click>=6.7,<7',
        'kubernetes>=4.0,<5'
    ],
    entry_points={
        'console_scripts': [
            'consulk8s = consulk8s:cli'
        ]
    },
    package_data={'': ['LICENSE', 'README.rst']},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: System :: Clustering',
        'Topic :: System :: Systems Administration'
    ]
)
