FROM openjdk:19-alpine AS emoji_csv

WORKDIR /apk

RUN wget https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.6.0.jar -O apktool.jar

COPY gboard.apk .

RUN java -jar apktool.jar d -o gboard.apk-decoded --no-src gboard.apk
RUN cat ./gboard.apk-decoded/res/raw/*.csv > emoji.csv

#####

FROM python as requirements_txt

WORKDIR /requirements

RUN pip install poetry
COPY pyproject.toml poetry.lock ./
RUN poetry export > requirements.txt

#####

FROM python AS emoji_kitchen_db

WORKDIR /emoji_kitchen_db

COPY --from=requirements_txt /requirements/requirements.txt .
RUN pip install -r requirements.txt && \
    rm requirements.txt

COPY --from=emoji_csv /apk/emoji.csv .
COPY emoji-kitchen-scan.py .

RUN sh -c 'python emoji-kitchen-scan.py emoji.csv emoji-kitchen.sqlite3'
