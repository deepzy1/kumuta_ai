"""Release the materialized analytics snapshot before response cleanup."""
import sqlite3
import unittest
from sqlalchemy import select
import test_api as fixture
from app import analytics
from app.database import SessionLocal,User,engine


class AnalyticsSnapshotTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.APITests.asyncSetUp
    asyncTearDown=fixture.APITests.asyncTearDown

    async def test_completed_report_does_not_block_another_connection_writer(self):
        uid=(await self.client.get('/auth/me',headers=self.headers)).json()['id']
        with SessionLocal() as db:
            user=db.get(User,uid)
            result=analytics.report(user,db,preset='today')
            # Keep the request session open, just as delayed dependency cleanup
            # does. A second connection must still commit immediately.
            with sqlite3.connect(engine.url.database,timeout=.2) as writer:
                writer.execute('UPDATE users SET allow_paid_models=allow_paid_models WHERE id=?',(uid,))
                writer.commit()
            self.assertFalse(db.in_transaction())
            self.assertEqual(result['workspace']['tasks'],0)
            self.assertEqual(fixture.FakeClient.calls,[])
