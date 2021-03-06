#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4; indent-tabs-mode: nil; coding: utf-8; -*-
# vim:set ft=python ts=4 sw=4 sts=4 autoindent:

'''
Authentication and authorization mechanisms.

Author:     Pontus Stenetorp    <pontus is s u-tokyo ac jp>
            Illes Solt          <solt tmit bme hu>
Version:    2011-04-21

TODO: Unittesting
'''

# future
from __future__ import absolute_import

# standard
from os.path import dirname, join as path_join, isdir, relpath
from hashlib import sha512


# arat
from arat.server.common import ProtocolError, deprecation
from config import USER_PASSWORD, DATA_DIR
from arat.server.message import Messager
from arat.server.projectconfig import ProjectConfiguration
from arat.server.common import JsonHandler

SALT = b"arat"


# To raise if the authority to carry out an operation is lacking
class NotAuthorisedError(ProtocolError):
    def __init__(self, attempted_action):
        ProtocolError.__init__(self)
        self.attempted_action = attempted_action

    def __str__(self):
        return 'Login required to perform "%s"' % self.attempted_action

    def json(self, json_dic):
        json_dic['exception'] = 'notAuthorised'
        return json_dic


# File/data access denial
class AccessDeniedError(ProtocolError):

    def __str__(self):
        return 'Access Denied'

    def json(self, json_dic):
        json_dic['exception'] = 'accessDenied'
        # TODO: Client should be responsible here
        Messager.error('Access Denied')
        return json_dic


def _is_authenticated(user, password):
    """
    Default authentication method is now sha512

    >>> _is_authenticated("admin", 'sha512:778589c8204ba29e44f0b2863ddc88751b451ddf38ed9e0c95ddfb12ff8283d43ca0362b4a8527deef0e7ac47f277a51bb235c23c2b6671650ba9f02ac583bf2')
    True

    For backward compatibility plain-text password is accepted but deprecated

    >>> _is_authenticated("admin-plaintext", "admin")
    True


    Password types can be mixed until the removal of plain text support

    >>> _is_authenticated("admin-plaintext", "sha512:778589c8204ba29e44f0b2863ddc88751b451ddf38ed9e0c95ddfb12ff8283d43ca0362b4a8527deef0e7ac47f277a51bb235c23c2b6671650ba9f02ac583bf2")
    True

    >>> _is_authenticated("admin", "admin")
    True


    Unknown users don't authenticate
    >>> _is_authenticated("me", "my password")
    False
    """
    # TODO: Replace with a database back-end
    if user in USER_PASSWORD:
        # client does not support password hash
        if not password.startswith("sha512:"):
            deprecation("Client send a password as plain text, this feature "
                        "will be removed in the next major release, "
                        "please use sha512 passwords.")
            password = "sha512:"+_password_hash(password)

        ref_password = USER_PASSWORD[user]
        # password stored in plain text
        if not USER_PASSWORD[user].startswith("sha512:"):
            deprecation("User password is stored as plain text, this feature "
                        "will be removed in the next major release"
                        "please use sha512 passwords.")
            ref_password = "sha512:"+_password_hash(USER_PASSWORD[user])

        return password == ref_password
    return False


def _password_hash(password):
    """
    >>> _password_hash("admin")
    '778589c8204ba29e44f0b2863ddc88751b451ddf38ed9e0c95ddfb12ff8283d43ca0362b4a8527deef0e7ac47f277a51bb235c23c2b6671650ba9f02ac583bf2'
    """
    password = password.encode("ascii")
    return sha512(SALT+password).hexdigest()


def allowed_to_read(real_path, user):
    data_path = path_join('/', relpath(real_path, DATA_DIR))
    # add trailing slash to directories, required to comply to robots.txt
    if isdir(real_path):
        data_path = '%s/' % data_path

    real_dir = dirname(real_path)
    robotparser = ProjectConfiguration(real_dir).get_access_control()
    if robotparser is None:
        return True  # default allow

    if user is None:
        user = b'guest'
    return robotparser.can_fetch(user, data_path)


class LoginHandler(JsonHandler):
    """
    Login user add set a cookie  accordingly
    """

    def _post(self, user, password):

        response = {}

        if not _is_authenticated(user, password):
            response["messages"] = ["Incorrect login and/or password"]
        else:
            self.set_secure_cookie("user", user)
            response["messages"] = ["Hello!"]

        return response


class LogoutHandler(JsonHandler):
    """
    Logout user by removing previously set cookie
    """

    def _post(self):

        response = {}

        self.clear_all_cookies()
        response["messages"] = ["Bye!"]

        return response


class WhoAmIHandler(JsonHandler):
    """
    Get current user name
    """

    def _post(self):

        response = {"user": self.get_secure_cookie("user")}

        return response
