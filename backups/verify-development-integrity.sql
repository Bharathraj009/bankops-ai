\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;
SELECT 'accounts' AS relation, count(*) FROM accounts
UNION ALL SELECT 'transfers', count(*) FROM transfers
UNION ALL SELECT 'ledger_entries', count(*) FROM ledger_entries
UNION ALL SELECT 'idempotency_records', count(*) FROM idempotency_records;
SELECT count(*) AS invalid_transfer_ledgers FROM transfers t
LEFT JOIN LATERAL (
    SELECT count(*) AS n,
        coalesce(sum(amount) FILTER (WHERE entry_type='DEBIT'),0) AS debit,
        coalesce(sum(amount) FILTER (WHERE entry_type='CREDIT'),0) AS credit,
        count(*) FILTER (WHERE
            (entry_type='DEBIT' AND account_id<>t.source_account_id) OR
            (entry_type='CREDIT' AND account_id<>t.destination_account_id) OR currency<>t.currency) AS invalid
    FROM ledger_entries WHERE transfer_id=t.id
) l ON true
WHERE l.debit<>l.credit OR l.invalid<>0 OR
    (l.n>0 AND (l.n<>2 OR l.debit<>t.amount)) OR
    (t.status='COMPLETED' AND l.n<>2) OR (t.status='FAILED' AND l.n<>0);
SELECT count(*) AS invalid_account_balances FROM accounts a
LEFT JOIN LATERAL (
    SELECT coalesce(sum(CASE WHEN entry_type='CREDIT' THEN amount ELSE -amount END),0) AS net
    FROM ledger_entries WHERE account_id=a.id
) l ON true
WHERE a.balance<>a.opening_balance+l.net OR a.balance<0 OR a.balance='NaN'::numeric
    OR a.opening_balance IS NULL OR a.opening_balance='NaN'::numeric;
SELECT count(*) AS orphan_postings FROM ledger_entries l
LEFT JOIN accounts a ON a.id=l.account_id LEFT JOIN transfers t ON t.id=l.transfer_id
WHERE a.id IS NULL OR t.id IS NULL;
SELECT coalesce(sum(CASE WHEN entry_type='CREDIT' THEN amount ELSE -amount END),0) AS ledger_net
FROM ledger_entries;
SELECT tgname, tgenabled, tgdeferrable, tginitdeferred FROM pg_trigger
WHERE NOT tgisinternal AND tgrelid IN ('accounts'::regclass,'transfers'::regclass,'ledger_entries'::regclass)
ORDER BY tgname;
COMMIT;
