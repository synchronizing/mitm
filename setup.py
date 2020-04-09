from distutils.core import setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="mitm",
    version="1.1",
    author="Felipe Faria",
    packages=["mitm"],
    install_requires=requirements,
    long_description=open("README.md").read(),
)
