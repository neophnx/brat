# -*- coding: utf-8; -*-
'''
Functionality for normalization SQL database access.
'''

# future
from __future__ import absolute_import
from __future__ import print_function

# standard
import sys
from os.path import join as path_join, exists, sep as path_sep
import sqlite3 as sqlite

from config import BASE_DIR, WORK_DIR

# Filename extension used for DB file.
DB_FILENAME_EXTENSION = 'db'

# Names of tables with information on each entry
TYPE_TABLES = ["names", "attributes", "infos"]

# Names of tables that must have some value for an entry
NON_EMPTY_TABLES = set(["names"])

# Maximum number of variables in one SQL query (TODO: get from lib!)
MAX_SQL_VARIABLE_COUNT = 999

__QUERY_COUNT = {}


class DbNotFoundError(Exception):
    """
    Report missing database file
    """

    def __init__(self, filename):
        """
        filename: string
        """
        Exception.__init__(self)
        self.filename = filename

    def __str__(self):
        return u'Database file "%s" not found' % self.filename

# Normalizes a given string for search. Used to implement
# case-insensitivity and similar in search.
# NOTE: this is a different sense of "normalization" than that
# implemented by a normalization DB as a whole: this just applies to
# single strings.
# NOTE2: it is critically important that this function is performed
# identically during DB initialization and actual lookup.
# TODO: enforce a single implementation.


def string_norm_form(string):
    """
    Normalize string for Database storage
    """
    return string.lower().strip().replace('-', ' ')


def __db_path(database):
    '''
    Given a DB name/path, returns the path for the file that is
    expected to contain the DB.
    '''
    # Assume we have a path relative to the arat root if the value
    # contains a separator, name only otherwise.
    # TODO: better treatment of name / path ambiguity, this doesn't
    # allow e.g. DBs to be located in arat root
    if path_sep in database:
        base = BASE_DIR
    else:
        base = WORK_DIR
    return path_join(base, database+'.'+DB_FILENAME_EXTENSION)


def reset_query_count(dbname):
    global __QUERY_COUNT
    __QUERY_COUNT[dbname] = 0


def get_query_count(dbname):
    global __QUERY_COUNT
    return __QUERY_COUNT.get(dbname, 0)


def __increment_query_count(dbname):
    global __QUERY_COUNT
    __QUERY_COUNT[dbname] = __QUERY_COUNT.get(dbname, 0) + 1


def _get_connection_cursor(dbname):
    """
    helper for DB access functions
    """
    filename = __db_path(dbname)

    # open DB
    if not exists(filename):
        raise DbNotFoundError(filename)
    connection = sqlite.connect(filename)
    cursor = connection.cursor()

    return connection, cursor


def _execute_fetchall(cursor, command, args, dbname):
    """
    helper for DB access functions
    """
    cursor.execute(command, args)
    __increment_query_count(dbname)
    return cursor.fetchall()


def data_by_id(dbname, id_):
    '''
    Given a DB name and an entity id, returns all the information
    contained in the DB for the id.
    '''
    _, cursor = _get_connection_cursor(dbname)

    # select separately from names, attributes and infos
    responses = {}
    for table in TYPE_TABLES:
        command = '''
                    SELECT L.text, N.value
                    FROM entities E
                    JOIN %s N
                      ON E.id = N.entity_id
                    JOIN labels L
                      ON L.id = N.label_id
                    WHERE E.uid=?''' % table
        responses[table] = _execute_fetchall(cursor, command, (id_, ), dbname)

        # short-circuit on missing or incomplete entry
        if table in NON_EMPTY_TABLES and len(responses[table]) == 0:
            break

    cursor.close()

    # empty or incomplete?
    for t in NON_EMPTY_TABLES:
        if len(responses[t]) == 0:
            return None

    # has content, format and return
    combined = []
    for t in TYPE_TABLES:
        combined.append(responses[t])
    return combined


def ids_by_name(dbname, name, exactmatch=False, return_match=False):
    return ids_by_names(dbname, [name], exactmatch, return_match)


def ids_by_names(dbname, names, exactmatch=False, return_match=False):
    result = []
    if len(names) < MAX_SQL_VARIABLE_COUNT:
        result = _ids_by_names(dbname, names, exactmatch, return_match)
    else:
        # break up into several queries
        i = 0
        while i < len(names):
            name = names[i:i+MAX_SQL_VARIABLE_COUNT]
            res = _ids_by_names(dbname, name, exactmatch, return_match)
            result.extend(res)
            i += MAX_SQL_VARIABLE_COUNT
    return result


def _ids_by_names(dbname, names, exactmatch=False, return_match=False):
    '''
    Given a DB name and a list of entity names, returns the ids of all
    entities having one of the given names. Uses exact string lookup
    if exactmatch is True, otherwise performs normalized string lookup
    (case-insensitive etc.). If return_match is True, returns pairs of
    (id, matched name), otherwise returns only ids.
    '''
    _, cursor = _get_connection_cursor(dbname)

    if not return_match:
        command = 'SELECT E.uid'
    else:
        command = 'SELECT E.uid, N.value'

    command += '''
FROM entities E
JOIN names N
  ON E.id = N.entity_id
'''
    if exactmatch:
        command += 'WHERE N.value IN (%s)' % ','.join(['?' for n in names])
    else:
        command += 'WHERE N.normvalue IN (%s)' % ','.join(['?' for n in names])
        names = [string_norm_form(n) for n in names]

    responses = _execute_fetchall(cursor, command, names, dbname)

    cursor.close()

    if not return_match:
        return [r[0] for r in responses]

    return [(r[0], r[1]) for r in responses]


def ids_by_name_attr(dbname, name, attr, exactmatch=False, return_match=False):
    return ids_by_names_attr(dbname, [name], attr, exactmatch, return_match)


def ids_by_names_attr(dbname, names, attr, exactmatch=False,
                      return_match=False):
    if len(names) < MAX_SQL_VARIABLE_COUNT-1:
        return _ids_by_names_attr(dbname, names, attr, exactmatch, return_match)
    # break up
    result = []
    i = 0
    while i < len(names):
        # -1 for attr
        name = names[i:i+MAX_SQL_VARIABLE_COUNT-1]
        res = _ids_by_names_attr(dbname, name, attr, exactmatch, return_match)
        result.extend(res)
        i += MAX_SQL_VARIABLE_COUNT-1
    return result


def _ids_by_names_attr(dbname, names, attr, exactmatch=False,
                       return_match=False):
    '''
    Given a DB name, a list of entity names, and an attribute text,
    returns the ids of all entities having one of the given names and
    an attribute matching the given attribute. Uses exact string
    lookup if exactmatch is True, otherwise performs normalized string
    lookup (case-insensitive etc.). If return_match is True, returns
    pairs of (id, matched name), otherwise returns only names.
    '''
    _, cursor = _get_connection_cursor(dbname)

    if not return_match:
        command = 'SELECT E.uid'
    else:
        command = 'SELECT E.uid, N.value'

    command += '''
FROM entities E
JOIN names N
  ON E.id = N.entity_id
JOIN attributes A
  ON E.id = A.entity_id
'''
    if exactmatch:
        command += 'WHERE N.value IN (%s) AND A.value=?' % ','.join([
            '?' for n in names])
    else:
        # NOTE: using 'LIKE', not '=' here
        command += 'WHERE N.normvalue IN (%s) AND A.normvalue LIKE ?' % ','.join([
            '?' for n in names])
        attr = '%'+string_norm_form(attr)+'%'
        names = [string_norm_form(n) for n in names]

    responses = _execute_fetchall(cursor, command, names + [attr], dbname)

    cursor.close()

    if not return_match:
        return [r[0] for r in responses]
    return [(r[0], r[1]) for r in responses]


def datas_by_ids(dbname, ids):
    if len(ids) < MAX_SQL_VARIABLE_COUNT:
        return _datas_by_ids(dbname, ids)
    # break up
    datas = {}
    i = 0
    ids = list(ids)
    while i < len(ids):
        ids_ = ids[i:i+MAX_SQL_VARIABLE_COUNT]
        res = _datas_by_ids(dbname, ids_)
        for j in res:
            datas[j] = res[j]
        i += MAX_SQL_VARIABLE_COUNT
    return datas


def _datas_by_ids(dbname, ids):
    '''
    Given a DB name and a list of entity ids, returns all the
    information contained in the DB for the ids.
    '''
    _, cursor = _get_connection_cursor(dbname)

    # select separately from names, attributes and infos
    responses = {}
    for table in TYPE_TABLES:
        command = '''
SELECT E.uid, L.text, N.value
FROM entities E
JOIN %s N
  ON E.id = N.entity_id
JOIN labels L
  ON L.id = N.label_id
WHERE E.uid IN (%s)''' % (table, ','.join(['?' for i in ids]))
        response = _execute_fetchall(cursor, command, list(ids), dbname)

        # group by ID first
        for id_, label, value in response:
            if id_ not in responses:
                responses[id_] = {}
            if table not in responses[id_]:
                responses[id_][table] = []
            responses[id_][table].append([label, value])

        # short-circuit on missing or incomplete entry
        if (table in NON_EMPTY_TABLES and
                len([i for i in responses if responses[i][table] == 0]) != 0):
            return None

    cursor.close()

    # empty or incomplete?
    for id_ in responses:
        for type_ in NON_EMPTY_TABLES:
            if len(responses[id_][type_]) == 0:
                return None

    # has expected content, format and return
    datas = {}
    for id_ in responses:
        datas[id_] = []
        for type_ in TYPE_TABLES:
            datas[id_].append(responses[id_].get(type_, []))
    return datas


def datas_by_name(dbname, name, exactmatch=False):
    # TODO: optimize
    datas = {}
    for id_ in ids_by_name(dbname, name, exactmatch):
        datas[id_] = data_by_id(dbname, id_)
    return datas


def main():
    """
    CLI for testing purpose
    """
    # test
    if len(sys.argv) > 1:
        dbname = sys.argv[1]
    else:
        dbname = "FMA"
    if len(sys.argv) > 2:
        id_ = sys.argv[2]
    else:
        id_ = "10883"
    print(data_by_id(dbname, id_))
    print(ids_by_name(dbname, 'Pleural branch of left sixth posterior intercostal artery'))
    print(datas_by_name(
        dbname, 'Pleural branch of left sixth posterior intercostal artery'))


if __name__ == "__main__":
    main()