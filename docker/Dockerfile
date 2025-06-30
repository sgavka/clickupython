FROM python:3.13

# setup code workdir
RUN mkdir /code
WORKDIR /code
COPY . /code/

# update pip
RUN pip install --upgrade pip

# install requiremnts
COPY requirements.txt /code/requirements.txt
RUN pip install --upgrade setuptools
RUN pip install -r /code/requirements.txt --upgrade

# entrypoint setup
COPY ./docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
