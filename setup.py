from setuptools import setup, find_packages

setup(
    name="wenku",
    version="0.2.1",
    packages=find_packages(),

    scripts=['./wenku.py'],

    install_requires=['requests>=2.0.0'],

    author="vinxv",
    author_email="vinuxcat@gmail.com",
    description="baidu wenku downloader",

    download_url='https://github.com/vinxv/wenku/archive/v0.2.tar.gz',
    url="https://github.com/vinxv/wenku",

    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    python_requires='>=3.6',
)
