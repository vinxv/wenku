from setuptools import setup, find_packages

setup(
    name="wenku",
    version="0.1",
    packages=find_packages(),

    scripts=['./wenku.py'],

    install_requires=['requests>=2.0.0'],

    author="vinxv",
    author_email="vinuxcat@gmail.com",
    description="baidu wenku downloader",
    keywords="baiduwenku downloader",
    url="https://github.com/vinxv/wenku",   # project home page, if any
    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6'
    ]
)
