# Locksmith Releases Infrastructure

AWS CDK (v2, TypeScript) for the `releases.keri.host` distribution endpoint.

## Prerequisites

- Node 20.x and pnpm 9.x
- AWS CLI v2 configured with credentials for the KERI.host AWS account
- `LOCKSMITH_AWS_ACCOUNT` environment variable set to the target account ID
- `LOCKSMITH_AWS_REGION` set to the primary region (defaults to `us-east-1`)
- Route 53 hosted zone for `keri.host` already provisioned in the same account
- One-time per account: `pnpm cdk bootstrap aws://ACCOUNT/us-east-1` and the primary region

## Stacks

| Stack | Region | Purpose |
|-------|--------|---------|
| `LocksmithReleasesCert` | us-east-1 | ACM certificate for `releases.keri.host` (CloudFront requires us-east-1) |
| `LocksmithReleasesBucket` | primary | S3 bucket `releases.keri.host` with origin-access identity |
| `LocksmithReleasesCdn` | primary | CloudFront distribution, three cache behaviors, branded 404 |
| `LocksmithReleasesDns` | primary | Route 53 A/AAAA alias records pointing at the distribution |
| `LocksmithReleasesIamOidc` | primary | GitHub OIDC provider + `gha-locksmith-release-publisher` role |

## Common commands

```bash
pnpm install
pnpm run synth       # synth cloudformation to cdk.out/
pnpm run diff        # compare to deployed state
pnpm run deploy      # deploy all stacks (cert + bucket first, then cdn + dns + iam)
pnpm test            # run snapshot + assertion tests
pnpm run test:update # accept new snapshots when stacks intentionally change
```

## Initial deployment order

CDK will sort stacks automatically based on dependencies, but the human-friendly order is:

1. Bootstrap both regions (`cdk bootstrap`)
2. Deploy `LocksmithReleasesCert` (will pause for DNS validation — automatically created in the parent zone)
3. Deploy `LocksmithReleasesBucket` and `LocksmithReleasesIamOidc`
4. Deploy `LocksmithReleasesCdn`
5. Deploy `LocksmithReleasesDns`

## Verification

After deployment:

```bash
aws s3 ls s3://releases.keri.host/
dig +short releases.keri.host
curl -I https://releases.keri.host/         # expect 403 (no default object) — that's correct
curl -I https://releases.keri.host/missing  # expect 404 with our branded page
```

The IAM role ARN is exported as `LocksmithPublisherRoleArn`; capture it for use in GitHub Actions OIDC configuration in later phases.
