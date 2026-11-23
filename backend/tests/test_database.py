import unittest

from app.database import sqlalchemy_url


class DatabaseUrlTests(unittest.TestCase):
    def test_railway_postgres_urls_use_installed_psycopg_driver(self):
        self.assertEqual(
            sqlalchemy_url("postgres://db-host/cryptosense"),
            "postgresql+psycopg://db-host/cryptosense",
        )
        self.assertEqual(
            sqlalchemy_url("postgresql://db-host/cryptosense"),
            "postgresql+psycopg://db-host/cryptosense",
        )
        self.assertEqual(
            sqlalchemy_url("postgresql+psycopg://db-host/cryptosense"),
            "postgresql+psycopg://db-host/cryptosense",
        )


if __name__ == "__main__":
    unittest.main()
