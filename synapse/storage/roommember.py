# -*- coding: utf-8 -*-
from twisted.internet import defer

from synapse.types import UserID
from synapse.api.constants import Membership
from synapse.persistence.tables import RoomMemberTable

from ._base import SQLBaseStore

import json
import logging


logger = logging.getLogger(__name__)


def last_row_id(cursor):
    return cursor.lastrowid


class RoomMemberStore(SQLBaseStore):

    @defer.inlineCallbacks
    def get_room_member(self, user_id=None, room_id=None):
        """Retrieve the current state of a room member.

        Args:
            user_id (str): The member's user ID.
            room_id (str): The room the member is in.
        Returns:
            namedtuple: The room member from the database, or None if this
            member does not exist.
        """
        query = RoomMemberTable.select_statement(
            "room_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1")
        res = yield self._db_pool.runInteraction(self.exec_single_with_result,
                query, RoomMemberTable.decode_results, room_id, user_id)
        if res:
            defer.returnValue(res[0])
        defer.returnValue(None)

    @defer.inlineCallbacks
    def store_room_member(self, user_id=None, room_id=None, membership=None,
                          content=None):
        """Store a room member in the database.

        Args:
            user_id (str): The member's user ID.
            room_id (str): The room in relation to the member.
            membership (synapse.api.constants.Membership): The new membership
            state.
            content (dict): The content of the membership (JSON).
        """

        content_json = json.dumps(content)
        query = ("INSERT INTO " + RoomMemberTable.table_name +
                "(user_id, room_id, membership, content) VALUES(?,?,?,?)")
        row = yield self._db_pool.runInteraction(self.exec_single_with_result,
                query, last_row_id, user_id, room_id, membership, content_json)
        defer.returnValue(row)

    @defer.inlineCallbacks
    def get_room_members(self, room_id=None, membership=None):
        """Retrieve the current room member list for a room.

        Args:
            room_id (str): The room to get the list of members.
            membership (synapse.api.constants.Membership): The filter to apply
            to this list, or None to return all members with some state
            associated with this room.
        Returns:
            list of namedtuples representing the members in this room.
        """
        query = ("SELECT *, MAX(id) FROM " + RoomMemberTable.table_name +
            " WHERE room_id = ? GROUP BY user_id")
        res = yield self._db_pool.runInteraction(self.exec_single_with_result,
                query, self._room_member_decode, room_id)
        # strip memberships which don't match
        if membership:
            res = [entry for entry in res if entry.membership == membership]
        defer.returnValue(res)

    def _room_member_decode(self, cursor):
        results = cursor.fetchall()
        # strip the MAX(id) column from the results so it can be made into
        # a namedtuple (which requires exactly the number of columns of the
        # table)
        entries = [t[0:-1] for t in results]
        return RoomMemberTable.decode_results(entries)

    @defer.inlineCallbacks
    def get_joined_hosts_for_room(self, room_id):
        query = (
            "SELECT *, MAX(id) FROM " + RoomMemberTable.table_name +
            " WHERE room_id = ? GROUP BY user_id"
        )

        res = yield self._db_pool.runInteraction(
            self.exec_single_with_result,
            query, self._room_member_decode, room_id
        )

        def host_from_user_id_string(user_id):
            domain = UserID.from_string(entry.user_id, self.hs).domain
            return domain

        # strip memberships which don't match
        hosts = [
            host_from_user_id_string(entry.user_id)
            for entry in res
            if entry.membership == Membership.JOIN
        ]

        logger.debug("Returning hosts: %s from results: %s", hosts, res)

        defer.returnValue(hosts)
