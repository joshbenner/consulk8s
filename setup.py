from setuptools import setup

tests_require = ['pytest']

setup(
    name='consulk8s',
    use_scm_version=True,
    py_modules=['consulk8s'],
    license='Proprietary',
    author='Josh Benner',
    author_email='joshb@aweber.com',
    description='Integrate Consul and Kubernetes',
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
    }
)
