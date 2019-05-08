from setuptools import setup


with open("requirements.txt") as requirements_file:
    requirements = requirements_file.read()

setup(
    name='PyGent',
    version='0.1',
    packages=['', 'algorithms', 'modeling_scripts','modeling_scripts/c_files'],
    package_data={'modeling_scripts/c_files': ['*.so']},
    url='https//github.com/mpritzkoleit/pygent',
    author='Max Pritzkoleit',
    author_email='Max.Pritzkoleit@tu-dresden.de',
    description = 'Python library for control and reinforcement learning',
    long_description='PyGent is a reinforcement learning library, '
                'that delivers a general framework, similar to OpenAIs "gym", for control and simulation of dynamic systems.'
                'It implements some state-of-the-art deep reinforcement learning and '
                'trajectory optimization algorithms.'
)
