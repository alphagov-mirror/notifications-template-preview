# notifications-template-preview

GOV.UK Notify template preview service

## Features of this application

 - Register and manage users
 - Create and manage services
 - Send batch emails and SMS by uploading a CSV
 - Show history of notifications

## First-time setup

### Docker

Since it's run in docker on PaaS, it's recommended that you use docker to run this locally.

```shell
  make prepare-docker-build-image
```

This will create the docker container and install the dependencies

### Local

It's possible to run locally though, in which case you'll need to install dependencies yourself

```shell
# binary dependencies
brew install imagemagick ghostscript cairo pango

mkvirtualenv -p /usr/local/bin/python3 notifications-python-client
pip install -r requirements.txt
```

This will
* create a virtual environment
* use pip to install dependencies.

## Tests

```shell
  make test-with-docker
```

or

```
  ./scripts/run_tests.sh
```
This script will run all the tests. [py.test](http://pytest.org/latest/) is used for testing.

Running tests will also apply syntax checking, using [pycodestyle](https://pypi.python.org/pypi/pycodestyle).


### Running the application

```shell
    make run-with-docker
```

If you want to run this manually, then

```shell
  workon notifications-template-preview
  ./scripts/run_app.sh
```


Then visit your app at `http://localhost:6013/_status`
