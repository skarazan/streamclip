import unittest
from unittest.mock import Mock, patch

import httpx

from worker import worker


class CreditContractTests(unittest.TestCase):
    def test_atomic_reservation_is_authoritative(self):
        response = Mock()
        response.json.return_value = [{"ok": True, "balance": 7}]
        job = {"id": "job-1", "user_id": "user-1"}
        with patch.object(worker, "sb", return_value=response) as request:
            self.assertEqual(worker.reserve_job_credits(job, 1), (True, 7))
        request.assert_called_once_with(
            "POST",
            "/rest/v1/rpc/reserve_job_credits",
            json={"p_job": "job-1", "p_user": "user-1", "p_amount": 1},
        )
        self.assertNotIn("_legacy_credit_cost", job)

    def test_pre_migration_single_worker_bridge_is_explicit(self):
        job = {"id": "job-2", "user_id": "user-2"}
        missing_rpc = httpx.HTTPStatusError(
            "missing RPC",
            request=httpx.Request("POST", "https://example.test/rpc"),
            response=httpx.Response(404),
        )
        with (
            patch.object(worker, "sb", side_effect=missing_rpc),
            patch.object(worker, "get_user", return_value={"credits": 2}),
        ):
            self.assertEqual(worker.reserve_job_credits(job, 1), (True, 1))
        self.assertEqual(job["_legacy_credit_cost"], 1)

    def test_pre_migration_bridge_still_refuses_empty_balance(self):
        job = {"id": "job-3", "user_id": "user-3"}
        missing_rpc = httpx.HTTPStatusError(
            "missing RPC",
            request=httpx.Request("POST", "https://example.test/rpc"),
            response=httpx.Response(404),
        )
        with (
            patch.object(worker, "sb", side_effect=missing_rpc),
            patch.object(worker, "get_user", return_value={"credits": 0}),
        ):
            self.assertEqual(worker.reserve_job_credits(job, 1), (False, 0))
        self.assertNotIn("_legacy_credit_cost", job)


class ContractFilesTests(unittest.TestCase):
    def test_claim_contract_limits_one_running_job_per_user(self):
        migration = (
            worker.Path(__file__).resolve().parents[1]
            / "infra/migrations/20260725_service_contract.sql"
        ).read_text()
        self.assertIn("active.user_id = candidate.user_id", migration)
        self.assertIn("active.status = 'running'", migration)
        self.assertIn("for update skip locked", migration)

    def test_editor_stream_contract_requires_partial_content(self):
        route = (
            worker.Path(__file__).resolve().parents[1]
            / "web/app/app/api/edit-jobs/[id]/media/route.js"
        ).read_text()
        self.assertIn('status: object.ContentRange ? 206 : 200', route)
        self.assertIn('"Content-Range"', route)
        self.assertIn('"Accept-Ranges"', route)


if __name__ == "__main__":
    unittest.main()
