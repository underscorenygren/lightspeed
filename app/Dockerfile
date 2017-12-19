FROM python:2.7.13

RUN mkdir -p /opt/app
WORKDIR /opt/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY *.py ./
EXPOSE 8080

ENTRYPOINT ["python"]
CMD ["server.py"]

