# Troubleshooting

## Slack / Bolt

- **`expired_trigger_id` / cold start:** First interaction after idle may fail; user retries usually succeed. Mitigations: **Lambda Function URLs** (less hop latency than API Gateway), EventBridge keep-warm, module-init DB/Fernet/Lambda-client warmup, lazy-listener self-invoke (zip apps), or provisioned concurrency if still tight on Slack’s 3s window.
- **Duplicate backblast / preblast in a channel:** Slack retried one `view_submission` after a slow ack (>3s). Each retry is a new Lambda; `beatdowns` uniqueness cannot help because it needs Slack’s `ts` from `chat_postMessage`. Slackblast INSERTs `view.id` into `interaction_claims` *before* posting; a 1062 skip is logged as `Skipping duplicate`. If extras reappear, confirm the table exists (below). Design: [ARCHITECTURE.md](ARCHITECTURE.md) (slackblast retry receipts).
- **INFO missing in CloudWatch (slackblast):** Bolt’s `clear_all_log_handlers()` strips Lambda’s root handler. The app must re-attach a `StreamHandler` or INFO lines never appear.
- **OAuth tables missing:** `db/migrations` creates `slack_bots`, `slack_installations` and `slack_oauth_states`. Run `python db/migrate.py --env-file .env.deploy.<stage> --check` to see whether the schema is behind (see [DEPLOY.md](DEPLOY.md#new-region-database)).

## Lambda

- **`AccessDeniedException` on self-invoke:** Ensure the function’s IAM role allows **`lambda:InvokeFunction`** on its own ARN (slackblast / qsignups lazy listeners).
- **Slow first Slack ack after keep-warm:** Keep-warm attaches a boto3 Lambda client onto Bolt’s `LambdaLazyListenerRunner` (not a throwaway client). Module-init warmup does the same so the first Slack ack does not construct a new client.

## Database

- **Encryption key mismatch:** `DB_ENCRYPTION_KEY` used at **migration** time must match **deploy** for that stage; otherwise reads fail or data looks corrupt.
- **QSignups cannot connect:** **`DATABASE_SCHEMA`** is required. The process does not fall back to Slack roles when it is unset.
- **`interaction_claims` missing:** Slackblast claim-before-post needs `interaction_claims` in `DATABASE_SCHEMA` (PK `claim_key` + `kind`). The region schema's copy or baseline creates it. A missing table fails closed (raises — does not post). Rows older than 7 days are pruned on each claim; do not truncate the table by hand while Slack may still retry a submit.

## PAXminer container upgrade

- Zip-to-container or image updates can fail if ECR permissions, image tags, or stack parameters drift. Check CloudFormation events and [DEPLOY.md](DEPLOY.md) PAXminer notes.

## Assets

- **Missing Strava images in S3:** Confirm **`IMAGE_S3_BUCKET`** and deploy-time upload; re-run image sync if documented for your stack.

## Still stuck?

Open an issue with **app name**, **environment** (test/prod), and **recent CloudWatch / SAM logs** (redact tokens).
