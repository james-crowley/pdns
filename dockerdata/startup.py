#!/usr/bin/env -S python3 -u
import os
import sys
import time
import jinja2

program = sys.argv[0].split('-')[0]
product = os.path.basename(program)

apienvvar = None
apiconftemplate = None
templateroot = '/etc/powerdns/templates.d'
templatedestination = ''
args = []

if product == 'pdns_recursor':
    args = ['--disable-syslog']
    apienvvar = 'PDNS_RECURSOR_API_KEY'
    apiconftemplate = """webserver
api-key={{ apikey }}
webserver-address=0.0.0.0
webserver-allow-from=0.0.0.0/0
webserver-password={{ apikey }}
    """
    templatedestination = '/etc/powerdns/recursor.d'
elif product == 'pdns_server':
    args = ['--disable-syslog']
    apienvvar = 'PDNS_AUTH_API_KEY'
    apiconftemplate = """webserver
api
api-key={{ apikey }}
webserver-address=0.0.0.0
webserver-allow-from=0.0.0.0/0
webserver-password={{ apikey }}
    """
    templatedestination = '/etc/powerdns/pdns.d'
elif product == 'dnsdist':
    args = ['--supervised', '--disable-syslog']
    apienvvar = 'DNSDIST_API_KEY'
    apiconftemplate = """webserver("0.0.0.0:8083", '{{ apikey }}', '{{ apikey }}', {}, '0.0.0.0/0')
controlSocket('0.0.0.0:5199')
setKey('{{ apikey }}')
setConsoleACL('0.0.0.0/0')
    """
    templateroot = '/etc/dnsdist/templates.d'
    templatedestination = '/etc/dnsdist/conf.d'

apikey = os.getenv(apienvvar)
if apikey is not None:
    webserver_conf = jinja2.Template(apiconftemplate).render(apikey=apikey)
    conffile = os.path.join(templatedestination, '_api.conf')
    with open(conffile, 'w') as f:
        f.write(webserver_conf)
    print("Created {} with content:\n{}\n".format(conffile, webserver_conf))

templates = os.getenv('TEMPLATE_FILES')
if templates is not None:
    for templateFile in templates.split(','):
        template = None
        with open(os.path.join(templateroot, templateFile + '.j2')) as f:
            template = jinja2.Template(f.read())
        rendered = template.render(os.environ)
        target = os.path.join(templatedestination, templateFile + '.conf')
        with open(target, 'w') as f:
            f.write(rendered)
        print("Created {} with content:\n{}\n".format(target, rendered))

if product == 'pdns_server':
    import psycopg2

    backend = os.getenv("PDNS_BACKEND")
    if backend is None:
        backend = "gsqlite3"

    if backend.lower() == "gpgsql":
        print("Configuring gpgsql backend....")

        print("Checking if environment variables are set....")
        if all(x is not None for x in [os.getenv("GPGSQL_DBNAME"), os.getenv("GPGSQL_HOST"), os.getenv("GPGSQL_PORT"),
                                       os.getenv("GPGSQL_USER"), os.getenv("GPGSQL_PASSWORD")]):
            print("Required environment variables set!")

            connection_timeout = 120
            connection = None
            print("Establishing connection with database....")
            while connection_timeout > 0:
                try:
                    connection = psycopg2.connect(dbname="postgres", user=os.getenv("GPGSQL_USER"),
                                                  password=os.getenv("GPGSQL_PASSWORD"), host=os.getenv("GPGSQL_HOST"),
                                                  port=os.getenv("GPGSQL_PORT"))
                    print("Database connection established!")
                    break
                except psycopg2.OperationalError:
                    print("Waiting for database connection...")
                    time.sleep(5)
                    connection_timeout = connection_timeout - 5
                    pass

            if connection is None:
                print("Could not established a connection to the database!")
                exit()

            connection.autocommit = True
            cursor = connection.cursor()

            cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{}'".format(os.getenv("GPGSQL_DBNAME")))
            created = cursor.fetchone()
            if not created:
                print("Creating a database named {}".format(os.getenv("GPGSQL_DBNAME")))
                cursor.execute("CREATE DATABASE {}".format(os.getenv("GPGSQL_DBNAME")))
            else:
                print("{} database already exists!".format(os.getenv("GPGSQL_DBNAME")))

            cursor.close()
            connection.close()

            connection = psycopg2.connect(dbname=os.getenv("GPGSQL_DBNAME"), user=os.getenv("GPGSQL_USER"),
                                          password=os.getenv("GPGSQL_PASSWORD"), host=os.getenv("GPGSQL_HOST"),
                                          port=os.getenv("GPGSQL_PORT"))
            cursor = connection.cursor()

            cursor.execute("select count(*) from information_schema.tables where table_schema = 'public'")
            number_of_tables = cursor.fetchone()

            if number_of_tables[0] == 0:
                print("Database is empty. Initializing SQL Schema....")
                with open("/usr/local/share/doc/pdns/schema.pgsql.sql", "r") as f:
                    cursor.execute(f.read())
                    connection.commit()

                print("Initialized Database!")
            else:
                print("Database already has tables! Skipping loading SQL Schema.")

            cursor.close()
            connection.close()

            print("Backend configured!")
        else:
            print("Required environment variables must be set!")
            print("GPGSQL_DBNAME: {} GPGSQL_HOST: {} GPGSQL_PORT: {} GPGSQL_USER: {} GPGSQL_PASSWORD: {}".format(
                os.getenv("GPGSQL_DBNAME"), os.getenv("GPGSQL_HOST"), os.getenv("GPGSQL_PORT"), os.getenv("GPGSQL_USER"),
                os.getenv("GPGSQL_PASSWORD")))
            exit()
    elif backend.lower() == "gmysql":
        print("Configuring gmysql.....")
    elif backend.lower() == "gsqlite3":
        print("Configuring gsqlite3.....")
    else:
        print("Backend, {}, is not currently supported".format(backend))

os.execv(program, [program]+args+sys.argv[1:])