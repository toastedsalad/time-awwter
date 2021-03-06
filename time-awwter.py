#!/usr/bin/env python3

# This script will iterate through a list of primary keys and print tracing messages for each request. The list specified with --pr-key-list is a new line separated list of primary keys.

# Execute like so:
# python3 time-awwter.py <host> <keyspace> <table> <name of the primary key> --user <username> --ssl-certificate <path to ssl cert> --ssl-key <path to ssl key> --pr-key-list <path to a list of primary keys>
# Optional parameters can be also specified in the settings.py file

# A lot of things were plagiarized from cassandra-trireme project https://github.com/fxlv/cassandra-trireme check it out. It's a good tool for counting rows and editing values at bulk.


# Pyton libs
from ssl import SSLContext, PROTOCOL_TLSv1, PROTOCOL_TLSv1_2
import argparse
import sys
import itertools
import time

# Cassandra related libs
from cassandra.cluster import Cluster, Session, ExecutionProfile, EXEC_PROFILE_DEFAULT, ConsistencyLevel
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import RoundRobinPolicy

# Settings
import settings

# A few datastructures that we're gonna use:
class CassandraSettings:

    def __init__(self):
        self.host = None
        self.port = None
        self.user = None
        self.password = None
        self.ssl_cert = None
        self.ssl_key = None
        self.ssl_version = None

class AppSettings:

    def __init__(self):
        self.pr_keys = None
        self.keyspace = None
        self.table = None
        self.chunk_size = None

class PrimaryKeys:
    def __init__(self):
        self.pr_keys_list = []

    def __getattr__(self, name):
        return getattr(self.pr_keys_list, name)
    
    @classmethod
    def pr_key_list_creator(cls, filename):
        self = cls()
        with open(filename, 'r') as f:
            for row in f:
                self.pr_keys_list.append(row.strip())
            return self

    def __len__(self):
        return len(self.pr_keys_list)

    def __iter__(self):
        return self.pr_keys_list.__iter__()


def parse_user_args():
    """This function is parsing command line arguments

    :return: Returns an instance with all arguments as attributes of parser.parse_args()
    :rtype: object
    """
    parser = argparse.ArgumentParser()
    parser.description = "Row reader for tracing and debugging"
    parser.add_argument("host", type=str, help="Cassandra host")
    parser.add_argument("keyspace", type=str, help="Keyspace to use")
    parser.add_argument("table", type=str, help="Table to use")
    parser.add_argument("key", type=str, help="Name of the primary key")
    parser.add_argument("--port",
                        type=int,
                        default=9042,
                        help="Cassandra port (9042 by default)")
    parser.add_argument("--user",
                        type=str,
                        default="cassandra",
                        help="Cassandra username")
    parser.add_argument("--password",
                        type=str,
                        help="DB password")    
    parser.add_argument("--ssl-certificate",
                        dest="ssl_cert",
                        type=str,
                        help="SSL certificate to use")
    parser.add_argument("--ssl-key",
                        dest="ssl_key",
                        type=str,
                        help="Key for the SSL certificate")
    parser.add_argument("--ssl-version",
                        type=str,
                        default="PROTOCOL_TLSv1_2",
                        dest="ssl_version",
                        help="Key for the SSL certificate")    
    parser.add_argument("--pr-key-list",
                        dest="pr_keys",
                        type=str,
                        help="A file with a list of primary keys separated by new line")
    parser.add_argument("--chunk-size",
                        type=int,
                        default=10,
                        dest="chunk_size",
                        help="Size of a chunk passed to async select")
    args = parser.parse_args()
    return args


def get_cassandra_session(host,
                          port,
                          user,
                          password,
                          ssl_cert,
                          ssl_key,
                          ssl_version):
    """A function that establishes a Cassandra connection

    :param host: Hostname of IP address
    :type host: str
    :param port: Port to connect to
    :type port: int
    :param user: Database user
    :type user: str
    :param password: Password for the database user
    :type password: str
    :param ssl_cert: Path to ssl_certificate
    :type ssl_cert: str
    :param ssl_key: Path to ssl_key
    :type ssl_key: str
    :param ssl_version: Version of the SSL environment used for the connection
    :type ssl_version: str
    :return: The function returns an instance for the cassandra session
    :rtype: object
    """
    auth_provider = PlainTextAuthProvider(username=user, password=password)

    ssl_options = {
        'certfile': ssl_cert,
        'keyfile': ssl_key,
        'ssl_version': PROTOCOL_TLSv1_2
        }

    policy = RoundRobinPolicy()

    profile = ExecutionProfile(
        consistency_level=ConsistencyLevel.LOCAL_ONE,
        load_balancing_policy=policy
        )

    cluster = Cluster([host], port=port, ssl_options=ssl_options, auth_provider=auth_provider, execution_profiles={EXEC_PROFILE_DEFAULT: profile})

    session = cluster.connect()
    return session


def execute_select(keyspace,
                    table,
                    key,
                    primary_keys,
                    session):
    """A function that executes a simple select with tracing enabled

    :param keyspace: Cassandra keyspace to select from
    :type keyspace: str
    :param table: Cassandra table to select from
    :type table: str
    :param primary_keys: List of primary keys
    :type primary_keys: instance
    :param session: Cassandra session
    :type session: object
    """

    sql_template="SELECT * FROM {}.{} WHERE {}=%s".format(keyspace, table, key)


# TODO This seems to be a better approach but I couldn't figure out how to print data retrieved from the query together with trace messages. It would be usefull to track what trace messages belong to which query.
#    result_list = []
#
#    for u in primary_keys:
#        result_list.append(session.execute_async(sql_template, [u], trace=True))
#    
#    for item in result_list:
#        rows = item.result()
#        trace = item.get_query_trace()
#        for e in trace.events:
#            print(e.source_elapsed, e.description)

    for u in primary_keys:
        try:
            result_list = []
            result_list.append(session.execute_async(sql_template, [u], trace=True))
            for item in result_list:
                rows = item.result()
                trace = item.get_query_trace()
                for e in trace.events:
                    print(u, e.source_elapsed, e.description)
                result_list = []
        except Exception as x:
            print("Exception when reading {}, exception message: {}".format(u, x.args[0]))
            sys.exit(1)

def chunked_iterable(iterable, size):
    """Generator object that chunks lists into smaller chunks

    :param iterable: Initial list to be chunked
    :type iterable: iterable object, list
    :param size: Amount of items in a chunk
    :type size: int
    :yield: A smaller list 
    :rtype: list of tuples
    """
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, size))
        if not chunk:
            break
        print(chunk)
        yield chunk


if __name__ == "__main__":

    # Instantiate the cassandra settings class
    cas_settings = CassandraSettings()    
    # Set attributes for the instance
    args = parse_user_args()

    # Some of the options can be specified in the settings.py
    cas_settings.host = args.host
    cas_settings.port = args.port

    if hasattr(settings, "db_user"):
        cas_settings.user = settings.db_user
    else:
        cas_settings.user = args.user

    if hasattr(settings, "db_password"):
        cas_settings.password = settings.db_password
    else:
        cas_settings.password = args.password

    if hasattr(settings, "ssl_cert"):
        cas_settings.ssl_cert = settings.ssl_cert
    else:
        cas_settings.ssl_cert = args.ssl_cert

    if hasattr(settings, "ssl_key"):
        cas_settings.ssl_key = settings.ssl_key
    else:
        cas_settings.ssl_key = args.ssl_key

    if hasattr(settings, "ssl_version"):
        cas_settings.ssl_version = settings.ssl_version
    else:
        cas_settings.ssl_version = args.ssl_version 

    # Instantiate appsettings class
    app_settings = AppSettings()
    # Set attributes for the app settings insantce
    app_settings.pr_keys = args.pr_keys
    app_settings.keyspace = args.keyspace
    app_settings.table = args.table
    app_settings.key = args.key
    app_settings.chunk_size = args.chunk_size

    # Instantiate a list of primary keys
    primary_keys = PrimaryKeys.pr_key_list_creator(app_settings.pr_keys)

    # Prepare the session object
    runtime_session = get_cassandra_session(cas_settings.host, cas_settings.port, cas_settings.user,  cas_settings.password, cas_settings.ssl_cert, cas_settings.ssl_key, cas_settings.ssl_version)

    # Execute the tracing select query
    for i in chunked_iterable(primary_keys, app_settings.chunk_size):
        execute_select(app_settings.keyspace, app_settings.table, app_settings.key, i, runtime_session)
