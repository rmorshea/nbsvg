from setuptools import setup

try:
    from jupyterpip import cmdclass
except:
    import pip, importlib
    pip.main(['install', 'jupyter-pip']); cmdclass = importlib.import_module('jupyterpip').cmdclass

setup(
    name='nbsvg',
    version='0.1',
    description='Implaments pythonic SVG in the IPython Notebook',
    author='Ryan Morshead',
    author_email='ryan.morshead@gmail.com',
    license='New BSD License',
    url='https://github.com/rmorshead/ipython-svg',
    keywords='data visualization svg python ipython widgets widget',
    classifiers=['Development Status :: 2 - Pre-Alpha',
                 'Programming Language :: Python',
                 'License :: OSI Approved :: MIT License'],
    packages=['nbsvg', 'nbsvg/py'],
    include_package_data=True,
    install_requires=["jupyter-pip"],
    cmdclass=cmdclass('nbsvg'),
)