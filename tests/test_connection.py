"""MongoDB 连接失败处理测试。"""

from __future__ import annotations

import unittest

from database.connection import check_connection, get_db
from utils.errors import DatabaseConnectionError, friendly_error


class ConnectionTests(unittest.TestCase):
    def test_connection_failure_is_friendly(self):
        status = check_connection(uri="mongodb://127.0.0.1:1/", database="foodlink_test_connection")
        self.assertFalse(status.ok)
        self.assertIn("MongoDB", status.message)
        self.assertNotIn("Traceback", status.message)

    def test_get_db_failure_raises_friendly_error(self):
        with self.assertRaises(DatabaseConnectionError) as ctx:
            get_db("foodlink_test_connection", uri="mongodb://127.0.0.1:1/", ping=True)
        message = friendly_error(ctx.exception)
        self.assertIn("MongoDB", message)
        self.assertNotIn("Traceback", message)


if __name__ == "__main__":
    unittest.main()

