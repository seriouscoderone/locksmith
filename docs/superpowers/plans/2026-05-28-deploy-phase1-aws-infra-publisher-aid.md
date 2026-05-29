# Locksmith Deploy Phase 1: AWS Infra + Publisher AID Bootstrap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision the AWS infrastructure for `releases.keri.host` (S3 + CloudFront + ACM + Route 53 + GitHub OIDC IAM role) and bootstrap the KERI publisher AID via a 2-of-3 multisig YubiKey ceremony, producing the embedded `publisher_anchor.json` consumed by all later phases.

**Architecture:** Two parallel deliverable tracks. Track A is an AWS CDK v2 (TypeScript) app in `infrastructure/` that deploys five stacks (cert, dns, bucket, cdn, iam-oidc). Track B is a `tools/publisher/` Python CLI skeleton, with the `incept` subcommand fully implemented and used in a one-time ceremony script that signs the multisig inception event, submits it to the api.keri.host witness pool, collects ≥`toad` receipts, and produces the committed `src/locksmith/release/publisher_anchor.json` trust anchor plus the S3-bound `publisher-aid.json` summary. **Phase 1 end state: the publisher AID is live, witnessed, with receipts persisted to S3.** The release-specific subcommands (`sign`, `countersign`, `submit`, `verify-ceremony`) are stubs in this phase; they are fully implemented in Phase 4. The `witness_client.py` HTTP client used for inception submission is also reused unchanged by Phase 4 for release `ixn` events. No app code changes yet.

**Tech Stack:**
- AWS CDK v2 (TypeScript, `aws-cdk-lib` 2.x), `pnpm`, `jest` for snapshot tests
- Python 3.14, `click`, `keripy` (already a project dependency), `python-fido2` for YubiKey HMAC/PIV interaction, `boto3` for S3 upload, `pytest` for tests
- AWS CLI v2 for verification commands
- This phase has **no upstream dependencies**. Phases 2/3/4 consume the outputs (`publisher_anchor.json`, S3 bucket, OIDC role).

**Spec sections covered:** §3 locked-in decisions (CDN domain, publisher entity, custodian model, witness pool, bundle ID), §6.1 S3 layout, §6.2 CloudFront behaviors, §7.1 publisher AID identity, §7.2 witness configuration, §7.5 signing workflow — *inception event only* (the release `ixn` signing workflow is owned by Phase 4; Phase 1 establishes the witness submission primitive `witness_client.py` and uses it to make the publisher AID live), §7.7 bootstrap trust, §11.2 new committed files (CDK + tools/publisher), §11.3 prerequisites (witness count, DNS).

---

## File Structure

**New files (Track A — AWS CDK):**

- `infrastructure/package.json` — pnpm package, depends on `aws-cdk-lib`, `constructs`, `jest`, `ts-jest`, `typescript`, `aws-cdk` CLI
- `infrastructure/pnpm-workspace.yaml` — declares this as a single-package workspace
- `infrastructure/tsconfig.json` — strict TypeScript config
- `infrastructure/cdk.json` — CDK app entry point + context (account, region)
- `infrastructure/jest.config.js` — jest with `ts-jest` preset, snapshot dir `__snapshots__/`
- `infrastructure/.gitignore` — `node_modules/`, `cdk.out/`, `*.d.ts`, `*.js`
- `infrastructure/bin/locksmith-releases.ts` — CDK app entry point, instantiates the 5 stacks
- `infrastructure/lib/config.ts` — environment + domain constants (`releases.keri.host`, account ID placeholder via env, regions `us-east-1` for cert/CDN and the parent account region for everything else)
- `infrastructure/lib/cert-stack.ts` — ACM cert for `releases.keri.host` in `us-east-1` (CloudFront requirement)
- `infrastructure/lib/dns-stack.ts` — Route 53 alias records (A + AAAA) pointing at CloudFront
- `infrastructure/lib/bucket-stack.ts` — S3 bucket `releases.keri.host` with OAI, no public access, versioning on
- `infrastructure/lib/cdn-stack.ts` — CloudFront distribution with the three cache behaviors (`releases/*` long TTL, `appcast/*` 60s, `publisher/*` 60s), HTTP/2 + HTTP/3, custom 404 response, OAI origin
- `infrastructure/lib/iam-oidc-stack.ts` — GitHub OIDC provider + `gha-locksmith-release-publisher` IAM role with scoped S3 write to `releases.keri.host` bucket
- `infrastructure/assets/404.html` — branded 404 page served by CloudFront for missing keys
- `infrastructure/test/cert-stack.test.ts` — snapshot test
- `infrastructure/test/dns-stack.test.ts` — snapshot test
- `infrastructure/test/bucket-stack.test.ts` — snapshot test + assertions on public-access-block + versioning
- `infrastructure/test/cdn-stack.test.ts` — snapshot test + assertion on the three cache behavior TTLs
- `infrastructure/test/iam-oidc-stack.test.ts` — snapshot test + assertion that role trust policy scopes to `repo:seriouscoderone/locksmith:*` and S3 permissions are bucket-scoped
- `infrastructure/README.md` — deploy instructions

**New files (Track B — Publisher CLI + ceremony):**

- `tools/publisher/pyproject.toml` — standalone package `locksmith-publisher`, depends on `click>=8.1`, `keri @ git+https://github.com/WebOfTrust/keripy.git`, `python-fido2>=1.1`, `boto3>=1.34`, `requests>=2.32`
- `tools/publisher/README.md` — short overview pointing to `docs/governance/publisher-ceremony.md`
- `tools/publisher/src/locksmith_publisher/__init__.py` — version constant
- `tools/publisher/src/locksmith_publisher/cli.py` — click command group + subcommands (`incept`, `sign`, `countersign`, `submit`, `verify-ceremony`); only `incept` is wired to real logic in this phase
- `tools/publisher/src/locksmith_publisher/yubikey.py` — wrapper around `python-fido2` PIV signing (Ed25519 via cryptography backend); shared by all signing subcommands
- `tools/publisher/src/locksmith_publisher/witnesses.py` — small helper that queries `api.keri.host` for its witness AID OOBIs
- `tools/publisher/src/locksmith_publisher/witness_client.py` — thin `requests`-based HTTP client for the api.keri.host witness pool (`submit_event`, `query_state`, `query_kel`); used in Phase 1 to submit the signed inception event and reused unchanged by Phase 4 for release `ixn` events
- `tools/publisher/src/locksmith_publisher/incept.py` — implements the 2-of-3 multisig inception event construction, signing, witness submission, and receipt persistence using keripy + witness_client
- `tools/publisher/src/locksmith_publisher/anchor.py` — emits `publisher_anchor.json` and the S3-bound `publisher-aid.json` summary
- `tools/publisher/ceremony/incept.py` — interactive ceremony runner (calls into `incept.py` and `anchor.py`); supports `--dry-run` against staging witnesses and `--submit`/`--no-submit`
- `tools/publisher/tests/__init__.py`
- `tools/publisher/tests/conftest.py` — fixtures: ephemeral keripy habery, fake witness pool
- `tools/publisher/tests/test_cli.py` — click runner tests for every subcommand
- `tools/publisher/tests/test_incept.py` — unit tests for 2-of-3 inception event construction, signature attachment, and witness submission (mocks `WitnessClient`)
- `tools/publisher/tests/test_witnesses.py` — unit tests for the witness query helper (mocks HTTP)
- `tools/publisher/tests/test_witness_client.py` — unit tests for the witness HTTP client (mocks `requests` to cover receipt collection, threshold-not-met, duplicity detection, unreachable network)
- `tools/publisher/tests/test_anchor.py` — unit tests for anchor file emission

**New files (committed app artifacts):**

- `src/locksmith/release/__init__.py` — empty namespace marker
- `src/locksmith/release/publisher_anchor.json` — trust anchor metadata; committed as a real file after the ceremony, but a placeholder schema-valid version is committed in this phase so app builds always have something to embed

**New files (docs):**

- `docs/governance/publisher-ceremony.md` — full runbook for inception + future release ceremonies
- `docs/governance/publisher-custodians.md` — placeholder for which device is in which physical location

**No modifications to existing files in Phase 1.** The release CI workflow (`.github/workflows/release.ci.yml`), `entitlements.plist`, `scripts/upload.py`, etc. are touched in later phases.

---

## Track A: AWS CDK Infrastructure

### Task A1: Initialize the CDK app structure

**Files:**
- Create: `infrastructure/package.json`
- Create: `infrastructure/pnpm-workspace.yaml`
- Create: `infrastructure/tsconfig.json`
- Create: `infrastructure/cdk.json`
- Create: `infrastructure/jest.config.js`
- Create: `infrastructure/.gitignore`

- [ ] **Step 1: Create `infrastructure/package.json`**

```json
{
  "name": "locksmith-releases-infrastructure",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "build": "tsc",
    "watch": "tsc -w",
    "test": "jest",
    "test:update": "jest -u",
    "cdk": "cdk",
    "synth": "cdk synth",
    "diff": "cdk diff",
    "deploy": "cdk deploy --all"
  },
  "devDependencies": {
    "@types/jest": "^29.5.12",
    "@types/node": "^20.11.0",
    "aws-cdk": "^2.140.0",
    "jest": "^29.7.0",
    "ts-jest": "^29.1.2",
    "ts-node": "^10.9.2",
    "typescript": "^5.4.5"
  },
  "dependencies": {
    "aws-cdk-lib": "^2.140.0",
    "constructs": "^10.3.0"
  }
}
```

- [ ] **Step 2: Create `infrastructure/pnpm-workspace.yaml`**

```yaml
packages:
  - "."
```

- [ ] **Step 3: Create `infrastructure/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["es2022"],
    "declaration": true,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitThis": true,
    "alwaysStrict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": false,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "inlineSourceMap": true,
    "inlineSources": true,
    "experimentalDecorators": true,
    "strictPropertyInitialization": false,
    "typeRoots": ["./node_modules/@types"],
    "resolveJsonModule": true,
    "esModuleInterop": true
  },
  "exclude": ["node_modules", "cdk.out"]
}
```

- [ ] **Step 4: Create `infrastructure/cdk.json`**

```json
{
  "app": "npx ts-node --prefer-ts-exts bin/locksmith-releases.ts",
  "watch": {
    "include": ["**"],
    "exclude": ["README.md", "cdk.*.out", "**/*.d.ts", "**/*.js", "tsconfig.json", "package*.json", "node_modules"]
  },
  "context": {
    "@aws-cdk/aws-iam:minimizePolicies": true,
    "@aws-cdk/core:stackRelativeExports": true,
    "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": true
  }
}
```

- [ ] **Step 5: Create `infrastructure/jest.config.js`**

```javascript
module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/test'],
  testMatch: ['**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  }
};
```

- [ ] **Step 6: Create `infrastructure/.gitignore`**

```
node_modules/
cdk.out/
*.d.ts
*.js
!jest.config.js
.env
.env.local
```

- [ ] **Step 7: Install dependencies and confirm tooling**

Run: `cd infrastructure && pnpm install && pnpm exec tsc --version && pnpm exec jest --version`
Expected: prints `Version 5.4.x` and `29.7.x` (or compatible)

- [ ] **Step 8: Commit**

```bash
git add infrastructure/package.json infrastructure/pnpm-workspace.yaml infrastructure/tsconfig.json infrastructure/cdk.json infrastructure/jest.config.js infrastructure/.gitignore
git commit -m "infra(phase1): scaffold CDK TypeScript app for releases.keri.host"
```

---

### Task A2: Shared config module

**Files:**
- Create: `infrastructure/lib/config.ts`

- [ ] **Step 1: Write the failing test**

Create: `infrastructure/test/config.test.ts`

```typescript
import { ReleasesConfig } from '../lib/config';

describe('ReleasesConfig', () => {
  test('reads the AWS account from LOCKSMITH_AWS_ACCOUNT env var', () => {
    process.env.LOCKSMITH_AWS_ACCOUNT = '111122223333';
    process.env.LOCKSMITH_AWS_REGION = 'us-west-2';
    const cfg = ReleasesConfig.fromEnv();
    expect(cfg.account).toBe('111122223333');
    expect(cfg.primaryRegion).toBe('us-west-2');
    expect(cfg.cloudfrontRegion).toBe('us-east-1');
  });

  test('throws if LOCKSMITH_AWS_ACCOUNT is not set', () => {
    delete process.env.LOCKSMITH_AWS_ACCOUNT;
    expect(() => ReleasesConfig.fromEnv()).toThrow(/LOCKSMITH_AWS_ACCOUNT/);
  });

  test('exposes the production domain and GitHub repo identifier', () => {
    process.env.LOCKSMITH_AWS_ACCOUNT = '111122223333';
    process.env.LOCKSMITH_AWS_REGION = 'us-east-1';
    const cfg = ReleasesConfig.fromEnv();
    expect(cfg.domainName).toBe('releases.keri.host');
    expect(cfg.parentZone).toBe('keri.host');
    expect(cfg.githubRepo).toBe('seriouscoderone/locksmith');
    expect(cfg.iamRoleName).toBe('gha-locksmith-release-publisher');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/config.test.ts`
Expected: FAIL with `Cannot find module '../lib/config'`

- [ ] **Step 3: Implement `infrastructure/lib/config.ts`**

```typescript
export interface ReleasesConfigOptions {
  account: string;
  primaryRegion: string;
}

export class ReleasesConfig {
  public static readonly DOMAIN_NAME = 'releases.keri.host';
  public static readonly PARENT_ZONE = 'keri.host';
  public static readonly GITHUB_REPO = 'seriouscoderone/locksmith';
  public static readonly IAM_ROLE_NAME = 'gha-locksmith-release-publisher';
  public static readonly CLOUDFRONT_REGION = 'us-east-1';

  public readonly account: string;
  public readonly primaryRegion: string;
  public readonly cloudfrontRegion: string;
  public readonly domainName: string;
  public readonly parentZone: string;
  public readonly githubRepo: string;
  public readonly iamRoleName: string;

  constructor(opts: ReleasesConfigOptions) {
    this.account = opts.account;
    this.primaryRegion = opts.primaryRegion;
    this.cloudfrontRegion = ReleasesConfig.CLOUDFRONT_REGION;
    this.domainName = ReleasesConfig.DOMAIN_NAME;
    this.parentZone = ReleasesConfig.PARENT_ZONE;
    this.githubRepo = ReleasesConfig.GITHUB_REPO;
    this.iamRoleName = ReleasesConfig.IAM_ROLE_NAME;
  }

  public static fromEnv(): ReleasesConfig {
    const account = process.env.LOCKSMITH_AWS_ACCOUNT;
    const region = process.env.LOCKSMITH_AWS_REGION ?? 'us-east-1';
    if (!account) {
      throw new Error('LOCKSMITH_AWS_ACCOUNT environment variable must be set');
    }
    return new ReleasesConfig({ account, primaryRegion: region });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd infrastructure && pnpm exec jest test/config.test.ts`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add infrastructure/lib/config.ts infrastructure/test/config.test.ts
git commit -m "infra(phase1): add releases config module with env-driven account"
```

---

### Task A3: ACM certificate stack (us-east-1)

**Files:**
- Create: `infrastructure/lib/cert-stack.ts`
- Create: `infrastructure/test/cert-stack.test.ts`

- [ ] **Step 1: Write the failing snapshot + assertion test**

Create: `infrastructure/test/cert-stack.test.ts`

```typescript
import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ReleasesConfig } from '../lib/config';
import { CertStack } from '../lib/cert-stack';

function makeStack(): CertStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  return new CertStack(app, 'TestCertStack', { config: cfg, env: { account: cfg.account, region: cfg.cloudfrontRegion } });
}

describe('CertStack', () => {
  test('matches snapshot', () => {
    const t = Template.fromStack(makeStack());
    expect(t.toJSON()).toMatchSnapshot();
  });

  test('creates a DNS-validated ACM cert for releases.keri.host in us-east-1', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CertificateManager::Certificate', {
      DomainName: 'releases.keri.host',
      ValidationMethod: 'DNS',
    });
  });

  test('exposes the cert ARN via stack output', () => {
    const t = Template.fromStack(makeStack());
    t.hasOutput('CertificateArn', Match.anyValue());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/cert-stack.test.ts`
Expected: FAIL with `Cannot find module '../lib/cert-stack'`

- [ ] **Step 3: Implement `infrastructure/lib/cert-stack.ts`**

```typescript
import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Certificate, CertificateValidation } from 'aws-cdk-lib/aws-certificatemanager';
import { HostedZone } from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';
import { ReleasesConfig } from './config';

export interface CertStackProps extends StackProps {
  readonly config: ReleasesConfig;
}

export class CertStack extends Stack {
  public readonly certificateArn: string;

  constructor(scope: Construct, id: string, props: CertStackProps) {
    super(scope, id, props);

    const zone = HostedZone.fromLookup(this, 'ParentZone', {
      domainName: props.config.parentZone,
    });

    const cert = new Certificate(this, 'ReleasesCertificate', {
      domainName: props.config.domainName,
      validation: CertificateValidation.fromDns(zone),
    });

    this.certificateArn = cert.certificateArn;

    new CfnOutput(this, 'CertificateArn', {
      value: cert.certificateArn,
      exportName: 'LocksmithReleasesCertificateArn',
    });
  }
}
```

- [ ] **Step 4: Run test to verify it passes (snapshot is created)**

Run: `cd infrastructure && pnpm exec jest test/cert-stack.test.ts`
Expected: PASS — 3 tests, 1 snapshot written

- [ ] **Step 5: Commit**

```bash
git add infrastructure/lib/cert-stack.ts infrastructure/test/cert-stack.test.ts infrastructure/test/__snapshots__/cert-stack.test.ts.snap
git commit -m "infra(phase1): add ACM cert stack for releases.keri.host"
```

---

### Task A4: S3 bucket stack with OAI

**Files:**
- Create: `infrastructure/lib/bucket-stack.ts`
- Create: `infrastructure/test/bucket-stack.test.ts`

- [ ] **Step 1: Write the failing tests**

Create: `infrastructure/test/bucket-stack.test.ts`

```typescript
import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ReleasesConfig } from '../lib/config';
import { BucketStack } from '../lib/bucket-stack';

function makeStack(): BucketStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  return new BucketStack(app, 'TestBucketStack', { config: cfg, env: { account: cfg.account, region: cfg.primaryRegion } });
}

describe('BucketStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates the releases.keri.host bucket with versioning and block-public-access', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::S3::Bucket', {
      BucketName: 'releases.keri.host',
      VersioningConfiguration: { Status: 'Enabled' },
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });

  test('creates an origin access identity', () => {
    const t = Template.fromStack(makeStack());
    t.resourceCountIs('AWS::CloudFront::CloudFrontOriginAccessIdentity', 1);
  });

  test('bucket policy grants OAI read but no public principals', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 's3:GetObject',
            Principal: Match.objectLike({ CanonicalUser: Match.anyValue() }),
          }),
        ]),
      }),
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/bucket-stack.test.ts`
Expected: FAIL with `Cannot find module '../lib/bucket-stack'`

- [ ] **Step 3: Implement `infrastructure/lib/bucket-stack.ts`**

```typescript
import { Stack, StackProps, RemovalPolicy, CfnOutput } from 'aws-cdk-lib';
import { Bucket, BlockPublicAccess, BucketEncryption } from 'aws-cdk-lib/aws-s3';
import { OriginAccessIdentity } from 'aws-cdk-lib/aws-cloudfront';
import { Construct } from 'constructs';
import { ReleasesConfig } from './config';

export interface BucketStackProps extends StackProps {
  readonly config: ReleasesConfig;
}

export class BucketStack extends Stack {
  public readonly bucket: Bucket;
  public readonly originAccessIdentity: OriginAccessIdentity;

  constructor(scope: Construct, id: string, props: BucketStackProps) {
    super(scope, id, props);

    this.bucket = new Bucket(this, 'ReleasesBucket', {
      bucketName: props.config.domainName,
      versioned: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      encryption: BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.originAccessIdentity = new OriginAccessIdentity(this, 'ReleasesOAI', {
      comment: `OAI for ${props.config.domainName}`,
    });

    this.bucket.grantRead(this.originAccessIdentity);

    new CfnOutput(this, 'ReleasesBucketName', {
      value: this.bucket.bucketName,
      exportName: 'LocksmithReleasesBucketName',
    });

    new CfnOutput(this, 'ReleasesBucketArn', {
      value: this.bucket.bucketArn,
      exportName: 'LocksmithReleasesBucketArn',
    });

    new CfnOutput(this, 'ReleasesOaiId', {
      value: this.originAccessIdentity.originAccessIdentityId,
      exportName: 'LocksmithReleasesOaiId',
    });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd infrastructure && pnpm exec jest test/bucket-stack.test.ts`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add infrastructure/lib/bucket-stack.ts infrastructure/test/bucket-stack.test.ts infrastructure/test/__snapshots__/bucket-stack.test.ts.snap
git commit -m "infra(phase1): add S3 bucket stack with OAI and block-public-access"
```

---

### Task A5: CloudFront distribution stack

**Files:**
- Create: `infrastructure/lib/cdn-stack.ts`
- Create: `infrastructure/assets/404.html`
- Create: `infrastructure/test/cdn-stack.test.ts`

- [ ] **Step 1: Write the 404 page**

Create `infrastructure/assets/404.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not found — releases.keri.host</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1115; color: #d8dee9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
  main { max-width: 32rem; padding: 2rem; }
  h1 { font-size: 2rem; margin: 0 0 0.5rem; }
  p { line-height: 1.5; color: #a0a8b8; }
  a { color: #8fbcff; }
</style>
</head>
<body>
<main>
  <h1>Not found</h1>
  <p>The release artifact you requested isn't here. Visit <a href="https://locksmith.app/">locksmith.app</a> for the current download.</p>
</main>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

Create: `infrastructure/test/cdn-stack.test.ts`

```typescript
import { App, Stack } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { OriginAccessIdentity } from 'aws-cdk-lib/aws-cloudfront';
import { Certificate } from 'aws-cdk-lib/aws-certificatemanager';
import { ReleasesConfig } from '../lib/config';
import { CdnStack } from '../lib/cdn-stack';

function makeStack(): CdnStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const supportStack = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  const bucket = new Bucket(supportStack, 'B', { bucketName: cfg.domainName });
  const oai = new OriginAccessIdentity(supportStack, 'O');
  const cert = Certificate.fromCertificateArn(supportStack, 'C', 'arn:aws:acm:us-east-1:111122223333:certificate/abc');
  return new CdnStack(app, 'TestCdnStack', {
    config: cfg,
    bucket,
    originAccessIdentity: oai,
    certificate: cert,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('CdnStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('uses HTTP/2 + HTTP/3 and TLS 1.2+', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        HttpVersion: 'http2and3',
        ViewerCertificate: Match.objectLike({ MinimumProtocolVersion: Match.stringLikeRegexp('TLSv1.2_2021') }),
        Aliases: ['releases.keri.host'],
      }),
    });
  });

  test('defines three cache behaviors with correct TTLs', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        CacheBehaviors: Match.arrayWith([
          Match.objectLike({ PathPattern: 'releases/*' }),
          Match.objectLike({ PathPattern: 'appcast/*' }),
          Match.objectLike({ PathPattern: 'publisher/*' }),
        ]),
      }),
    });
  });

  test('declares a 404 custom error response', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        CustomErrorResponses: Match.arrayWith([
          Match.objectLike({ ErrorCode: 404, ResponsePagePath: '/404.html' }),
        ]),
      }),
    });
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/cdn-stack.test.ts`
Expected: FAIL with `Cannot find module '../lib/cdn-stack'`

- [ ] **Step 4: Implement `infrastructure/lib/cdn-stack.ts`**

```typescript
import { Stack, StackProps, Duration, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import {
  Distribution,
  ViewerProtocolPolicy,
  HttpVersion,
  SecurityPolicyProtocol,
  AllowedMethods,
  CachedMethods,
  CachePolicy,
  PriceClass,
  OriginAccessIdentity,
  ErrorResponse,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3Origin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { ICertificate } from 'aws-cdk-lib/aws-certificatemanager';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';
import { ReleasesConfig } from './config';

export interface CdnStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly bucket: Bucket;
  readonly originAccessIdentity: OriginAccessIdentity;
  readonly certificate: ICertificate;
}

export class CdnStack extends Stack {
  public readonly distribution: Distribution;

  constructor(scope: Construct, id: string, props: CdnStackProps) {
    super(scope, id, props);

    const origin = new S3Origin(props.bucket, {
      originAccessIdentity: props.originAccessIdentity,
    });

    const longTtlPolicy = new CachePolicy(this, 'ImmutableArtifactCachePolicy', {
      cachePolicyName: 'LocksmithReleasesImmutable',
      defaultTtl: Duration.days(365),
      minTtl: Duration.days(365),
      maxTtl: Duration.days(3650),
      enableAcceptEncodingGzip: false,
      enableAcceptEncodingBrotli: false,
    });

    const shortTtlPolicy = new CachePolicy(this, 'ShortLivedCachePolicy', {
      cachePolicyName: 'LocksmithReleasesShortLived',
      defaultTtl: Duration.seconds(60),
      minTtl: Duration.seconds(0),
      maxTtl: Duration.seconds(60),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
    });

    const errorResponses: ErrorResponse[] = [
      {
        httpStatus: 404,
        responseHttpStatus: 404,
        responsePagePath: '/404.html',
        ttl: Duration.seconds(60),
      },
    ];

    this.distribution = new Distribution(this, 'ReleasesDistribution', {
      domainNames: [props.config.domainName],
      certificate: props.certificate,
      defaultBehavior: {
        origin,
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: shortTtlPolicy,
        allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        cachedMethods: CachedMethods.CACHE_GET_HEAD,
      },
      additionalBehaviors: {
        'releases/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: longTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
        'appcast/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: shortTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
        'publisher/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: shortTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
      },
      httpVersion: HttpVersion.HTTP2_AND_3,
      minimumProtocolVersion: SecurityPolicyProtocol.TLS_V1_2_2021,
      priceClass: PriceClass.PRICE_CLASS_100,
      errorResponses,
      defaultRootObject: '',
      comment: 'Locksmith releases distribution',
    });

    new BucketDeployment(this, 'Deploy404', {
      destinationBucket: props.bucket,
      sources: [Source.asset(path.join(__dirname, '..', 'assets'))],
      retainOnDelete: false,
      prune: false,
    });

    new CfnOutput(this, 'DistributionId', {
      value: this.distribution.distributionId,
      exportName: 'LocksmithReleasesDistributionId',
    });

    new CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
      exportName: 'LocksmithReleasesDistributionDomain',
    });
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd infrastructure && pnpm exec jest test/cdn-stack.test.ts`
Expected: PASS — 4 tests

- [ ] **Step 6: Commit**

```bash
git add infrastructure/lib/cdn-stack.ts infrastructure/assets/404.html infrastructure/test/cdn-stack.test.ts infrastructure/test/__snapshots__/cdn-stack.test.ts.snap
git commit -m "infra(phase1): add CloudFront distribution with cache behaviors and 404 page"
```

---

### Task A6: Route 53 DNS stack

**Files:**
- Create: `infrastructure/lib/dns-stack.ts`
- Create: `infrastructure/test/dns-stack.test.ts`

- [ ] **Step 1: Write the failing tests**

Create: `infrastructure/test/dns-stack.test.ts`

```typescript
import { App, Stack } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { Distribution } from 'aws-cdk-lib/aws-cloudfront';
import { ReleasesConfig } from '../lib/config';
import { DnsStack } from '../lib/dns-stack';

function makeStack(): DnsStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const support = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  // Synthesize a fake distribution to pass in.
  const dist = {
    distributionDomainName: 'd123abc.cloudfront.net',
  } as unknown as Distribution;
  return new DnsStack(app, 'TestDnsStack', {
    config: cfg,
    distribution: dist,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('DnsStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates A and AAAA alias records for releases.keri.host', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'releases.keri.host.',
      Type: 'A',
    });
    t.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'releases.keri.host.',
      Type: 'AAAA',
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/dns-stack.test.ts`
Expected: FAIL with `Cannot find module '../lib/dns-stack'`

- [ ] **Step 3: Implement `infrastructure/lib/dns-stack.ts`**

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { ARecord, AaaaRecord, HostedZone, RecordTarget } from 'aws-cdk-lib/aws-route53';
import { CloudFrontTarget } from 'aws-cdk-lib/aws-route53-targets';
import { IDistribution } from 'aws-cdk-lib/aws-cloudfront';
import { ReleasesConfig } from './config';

export interface DnsStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly distribution: IDistribution;
}

export class DnsStack extends Stack {
  constructor(scope: Construct, id: string, props: DnsStackProps) {
    super(scope, id, props);

    const zone = HostedZone.fromLookup(this, 'ParentZone', {
      domainName: props.config.parentZone,
    });

    const target = RecordTarget.fromAlias(new CloudFrontTarget(props.distribution));

    new ARecord(this, 'ReleasesA', {
      zone,
      recordName: 'releases',
      target,
    });

    new AaaaRecord(this, 'ReleasesAAAA', {
      zone,
      recordName: 'releases',
      target,
    });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd infrastructure && pnpm exec jest test/dns-stack.test.ts`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add infrastructure/lib/dns-stack.ts infrastructure/test/dns-stack.test.ts infrastructure/test/__snapshots__/dns-stack.test.ts.snap
git commit -m "infra(phase1): add Route 53 A/AAAA alias records for releases.keri.host"
```

---

### Task A7: GitHub OIDC IAM role stack

**Files:**
- Create: `infrastructure/lib/iam-oidc-stack.ts`
- Create: `infrastructure/test/iam-oidc-stack.test.ts`

- [ ] **Step 1: Write the failing tests**

Create: `infrastructure/test/iam-oidc-stack.test.ts`

```typescript
import { App, Stack } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { ReleasesConfig } from '../lib/config';
import { IamOidcStack } from '../lib/iam-oidc-stack';

function makeStack(): IamOidcStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const support = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  const bucket = new Bucket(support, 'B', { bucketName: cfg.domainName });
  return new IamOidcStack(app, 'TestIamOidcStack', {
    config: cfg,
    releasesBucket: bucket,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('IamOidcStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates the GitHub OIDC provider with the correct issuer', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::IAM::OIDCProvider', {
      Url: 'https://token.actions.githubusercontent.com',
      ClientIdList: ['sts.amazonaws.com'],
    });
  });

  test('creates the gha-locksmith-release-publisher role scoped to the repo', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::IAM::Role', {
      RoleName: 'gha-locksmith-release-publisher',
      AssumeRolePolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Condition: Match.objectLike({
              StringLike: Match.objectLike({
                'token.actions.githubusercontent.com:sub': Match.arrayWith([
                  Match.stringLikeRegexp('repo:seriouscoderone/locksmith:.*'),
                ]),
              }),
            }),
          }),
        ]),
      }),
    });
  });

  test('role policy is scoped to the releases bucket only', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith(['s3:PutObject', 's3:GetObject']),
            Resource: Match.arrayWith([
              Match.stringLikeRegexp('arn:aws:s3:::releases.keri.host/.*'),
            ]),
          }),
        ]),
      }),
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/iam-oidc-stack.test.ts`
Expected: FAIL with `Cannot find module '../lib/iam-oidc-stack'`

- [ ] **Step 3: Implement `infrastructure/lib/iam-oidc-stack.ts`**

```typescript
import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  OpenIdConnectProvider,
  Role,
  WebIdentityPrincipal,
  PolicyStatement,
  Effect,
} from 'aws-cdk-lib/aws-iam';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { ReleasesConfig } from './config';

export interface IamOidcStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly releasesBucket: Bucket;
}

export class IamOidcStack extends Stack {
  public readonly publisherRole: Role;

  constructor(scope: Construct, id: string, props: IamOidcStackProps) {
    super(scope, id, props);

    const provider = new OpenIdConnectProvider(this, 'GithubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    const principal = new WebIdentityPrincipal(provider.openIdConnectProviderArn, {
      StringEquals: {
        'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
      },
      StringLike: {
        'token.actions.githubusercontent.com:sub': [
          `repo:${props.config.githubRepo}:ref:refs/tags/v*`,
          `repo:${props.config.githubRepo}:ref:refs/heads/main`,
          `repo:${props.config.githubRepo}:ref:refs/heads/development`,
          `repo:${props.config.githubRepo}:environment:release`,
        ],
      },
    });

    this.publisherRole = new Role(this, 'PublisherRole', {
      roleName: props.config.iamRoleName,
      assumedBy: principal,
      description: 'GitHub Actions role for uploading Locksmith releases to S3',
    });

    this.publisherRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        's3:PutObject',
        's3:PutObjectAcl',
        's3:GetObject',
        's3:DeleteObject',
        's3:ListBucket',
      ],
      resources: [
        props.releasesBucket.bucketArn,
        `${props.releasesBucket.bucketArn}/*`,
      ],
    }));

    new CfnOutput(this, 'PublisherRoleArn', {
      value: this.publisherRole.roleArn,
      exportName: 'LocksmithPublisherRoleArn',
    });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd infrastructure && pnpm exec jest test/iam-oidc-stack.test.ts`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add infrastructure/lib/iam-oidc-stack.ts infrastructure/test/iam-oidc-stack.test.ts infrastructure/test/__snapshots__/iam-oidc-stack.test.ts.snap
git commit -m "infra(phase1): add GitHub OIDC IAM role with bucket-scoped S3 write"
```

---

### Task A8: CDK app entry point wiring the five stacks

**Files:**
- Create: `infrastructure/bin/locksmith-releases.ts`

- [ ] **Step 1: Write the failing integration test**

Create: `infrastructure/test/app-synth.test.ts`

```typescript
import { execSync } from 'child_process';
import * as path from 'path';

describe('cdk app', () => {
  test('synthesizes all five stacks without error', () => {
    const out = execSync('npx cdk synth --quiet', {
      cwd: path.resolve(__dirname, '..'),
      env: {
        ...process.env,
        LOCKSMITH_AWS_ACCOUNT: '111122223333',
        LOCKSMITH_AWS_REGION: 'us-east-1',
        CDK_DEFAULT_ACCOUNT: '111122223333',
        CDK_DEFAULT_REGION: 'us-east-1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    }).toString();
    expect(out).toContain('LocksmithReleasesCert');
    expect(out).toContain('LocksmithReleasesBucket');
    expect(out).toContain('LocksmithReleasesCdn');
    expect(out).toContain('LocksmithReleasesDns');
    expect(out).toContain('LocksmithReleasesIamOidc');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd infrastructure && pnpm exec jest test/app-synth.test.ts`
Expected: FAIL — `cdk synth` errors because `bin/locksmith-releases.ts` is missing

- [ ] **Step 3: Implement `infrastructure/bin/locksmith-releases.ts`**

```typescript
#!/usr/bin/env node
import 'source-map-support/register';
import { App } from 'aws-cdk-lib';
import { ReleasesConfig } from '../lib/config';
import { CertStack } from '../lib/cert-stack';
import { BucketStack } from '../lib/bucket-stack';
import { CdnStack } from '../lib/cdn-stack';
import { DnsStack } from '../lib/dns-stack';
import { IamOidcStack } from '../lib/iam-oidc-stack';

const app = new App();
const config = ReleasesConfig.fromEnv();

const primaryEnv = { account: config.account, region: config.primaryRegion };
const cloudfrontEnv = { account: config.account, region: config.cloudfrontRegion };

const cert = new CertStack(app, 'LocksmithReleasesCert', {
  config,
  env: cloudfrontEnv,
  crossRegionReferences: true,
});

const bucket = new BucketStack(app, 'LocksmithReleasesBucket', {
  config,
  env: primaryEnv,
  crossRegionReferences: true,
});

const cdn = new CdnStack(app, 'LocksmithReleasesCdn', {
  config,
  bucket: bucket.bucket,
  originAccessIdentity: bucket.originAccessIdentity,
  certificate: cert.node.findChild('ReleasesCertificate') as any,
  env: primaryEnv,
  crossRegionReferences: true,
});
cdn.addDependency(cert);
cdn.addDependency(bucket);

const dns = new DnsStack(app, 'LocksmithReleasesDns', {
  config,
  distribution: cdn.distribution,
  env: primaryEnv,
  crossRegionReferences: true,
});
dns.addDependency(cdn);

const iamOidc = new IamOidcStack(app, 'LocksmithReleasesIamOidc', {
  config,
  releasesBucket: bucket.bucket,
  env: primaryEnv,
});
iamOidc.addDependency(bucket);

app.synth();
```

- [ ] **Step 4: Add `source-map-support` to dev dependencies**

```bash
cd infrastructure && pnpm add -D source-map-support @types/source-map-support
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd infrastructure && pnpm exec jest test/app-synth.test.ts`
Expected: PASS — all five stacks present in synth output

- [ ] **Step 6: Run the full infra test suite**

Run: `cd infrastructure && pnpm exec jest`
Expected: All tests pass (~17 across files + snapshots)

- [ ] **Step 7: Commit**

```bash
git add infrastructure/bin/locksmith-releases.ts infrastructure/test/app-synth.test.ts infrastructure/package.json infrastructure/pnpm-lock.yaml
git commit -m "infra(phase1): wire CDK app entry point with cert/bucket/cdn/dns/iam stacks"
```

---

### Task A9: Infrastructure README

**Files:**
- Create: `infrastructure/README.md`

- [ ] **Step 1: Write the README**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/README.md
git commit -m "infra(phase1): add infrastructure README with deploy runbook"
```

---

## Track B: Publisher CLI skeleton + AID inception

### Task B1: `tools/publisher/` package skeleton

**Files:**
- Create: `tools/publisher/pyproject.toml`
- Create: `tools/publisher/README.md`
- Create: `tools/publisher/src/locksmith_publisher/__init__.py`
- Create: `tools/publisher/tests/__init__.py`

- [ ] **Step 1: Create `tools/publisher/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "locksmith-publisher"
version = "0.1.0"
description = "KERI publisher signing CLI for Locksmith releases (off-CI, custodian devices only)"
readme = "README.md"
requires-python = ">=3.14.0"
license = { text = "MIT" }

authors = [
    { name = "Joseph Lee Hunsaker", email = "joseph.hunsaker@usurance.com" }
]

dependencies = [
    "click>=8.1",
    "keri @ git+https://github.com/WebOfTrust/keripy.git",
    "python-fido2>=1.1",
    "boto3>=1.34",
    "requests>=2.32",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "responses>=0.25",
]

[project.scripts]
locksmith-publisher = "locksmith_publisher.cli:cli"

[tool.setuptools.packages.find]
where = ["src"]
include = ["locksmith_publisher*"]

[tool.setuptools.package-dir]
"" = "src"

[tool.pytest.ini_options]
pythonpath = ["src", "."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `tools/publisher/README.md`**

```markdown
# locksmith-publisher

The off-CI signing CLI for Locksmith releases. **Never installed in CI.** Only runs on custodian devices (laptop YubiKey, desktop YubiKey, air-gapped backup) that hold KERI signing keys for the publisher AID.

See [`docs/governance/publisher-ceremony.md`](../../docs/governance/publisher-ceremony.md) for the full ceremony runbook.

## Install (custodian devices only)

```bash
cd tools/publisher
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
locksmith-publisher --help
```

## Subcommands

| Command | Status (Phase 1) | Purpose |
|---------|------------------|---------|
| `incept` | implemented | One-time: bootstrap the 2-of-3 multisig publisher AID |
| `sign` | stub | Phase 4: signer 1 produces partial release anchor signature |
| `countersign` | stub | Phase 4: signer 2 adds second signature to reach 2-of-3 quorum |
| `submit` | stub | Phase 4: submit signed anchor + collect witness receipts, upload to S3 |
| `verify-ceremony` | stub | Phase 4: re-verify a finalized anchor against witnesses |
```

- [ ] **Step 3: Create `tools/publisher/src/locksmith_publisher/__init__.py`**

```python
"""Locksmith publisher signing CLI.

Off-CI tool. Holds publisher AID signing keys via YubiKey or air-gapped device.
Never runs in continuous integration.
"""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create `tools/publisher/tests/__init__.py` (empty)**

```python
```

- [ ] **Step 5: Install the package and confirm**

Run: `cd tools/publisher && python3.14 -m venv .venv && source .venv/bin/activate && pip install -e ".[test]" && python -c "import locksmith_publisher; print(locksmith_publisher.__version__)"`
Expected: prints `0.1.0`

- [ ] **Step 6: Commit**

```bash
git add tools/publisher/pyproject.toml tools/publisher/README.md tools/publisher/src/locksmith_publisher/__init__.py tools/publisher/tests/__init__.py
git commit -m "publisher(phase1): scaffold tools/publisher Python package"
```

---

### Task B2: Click CLI with stubbed subcommands

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/cli.py`
- Create: `tools/publisher/tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Create: `tools/publisher/tests/test_cli.py`

```python
from click.testing import CliRunner

from locksmith_publisher.cli import cli


def test_cli_help_lists_all_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("incept", "sign", "countersign", "submit", "verify-ceremony"):
        assert cmd in result.output


def test_cli_version_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_sign_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["sign", "--version", "1.0.0"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_countersign_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["countersign", "--partial", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_submit_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["submit", "--signed", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_verify_ceremony_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-ceremony", "--anchor", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith_publisher.cli'`

- [ ] **Step 3: Implement `tools/publisher/src/locksmith_publisher/cli.py`**

```python
"""Click CLI entry point for locksmith-publisher.

Only the `incept` subcommand is fully implemented in Phase 1.
The release signing subcommands are stubs that fail loudly until Phase 4.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__


def _not_yet(name: str) -> None:
    click.echo(
        f"`{name}` is not implemented in Phase 1. It will be added in Phase 4 "
        "(release signing ceremony).",
        err=True,
    )
    sys.exit(2)


@click.group()
@click.version_option(__version__, prog_name="locksmith-publisher")
def cli() -> None:
    """Off-CI signing CLI for Locksmith releases."""


@cli.command("incept")
@click.option("--witness-pool-oobi", required=True, multiple=True,
              help="OOBI URL of a witness AID to include in the inception event. Repeat for each witness (>=3 required).")
@click.option("--toad", type=int, default=2, show_default=True,
              help="Threshold of accountable duplicity (number of witness receipts required).")
@click.option("--quorum", type=int, default=2, show_default=True,
              help="Signer quorum required (2-of-3 by default).")
@click.option("--signers", type=int, default=3, show_default=True,
              help="Total number of signer devices.")
@click.option("--dry-run/--production", default=True, show_default=True,
              help="--dry-run uses ephemeral staging witnesses and writes outputs to a tmp dir. --production targets the real publisher.")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), required=True,
              help="Directory where publisher_anchor.json and KEL artifacts are written.")
@click.option("--yubikey-slots", multiple=True, default=("9c", "9c", "9c"), show_default=True,
              help="PIV slot identifier for each signer device. Default 9c (Digital Signature). Provide once per signer.")
def incept_cmd(
    witness_pool_oobi: tuple[str, ...],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: tuple[str, ...],
) -> None:
    """Bootstrap the 2-of-3 multisig publisher AID. One-time ceremony."""
    from .incept import run_inception_ceremony

    run_inception_ceremony(
        witness_oobis=list(witness_pool_oobi),
        toad=toad,
        quorum=quorum,
        signers=signers,
        dry_run=dry_run,
        output_dir=output_dir,
        yubikey_slots=list(yubikey_slots),
    )


@cli.command("sign")
@click.option("--version", required=True, help="Release version string (X.Y.Z).")
@click.option("--candidates-url", required=True, help="S3 URL of the release-candidate.json from CI.")
def sign_cmd(version: str, candidates_url: str) -> None:
    """[Phase 4] Signer 1: produce a partial release-anchor signature."""
    _not_yet("sign")


@cli.command("countersign")
@click.option("--partial", required=True, type=click.Path(exists=False),
              help="Path to release-anchor-X.Y.Z.partial.cesr produced by `sign`.")
def countersign_cmd(partial: str) -> None:
    """[Phase 4] Signer 2: add the second signature to reach quorum."""
    _not_yet("countersign")


@cli.command("submit")
@click.option("--signed", required=True, type=click.Path(exists=False),
              help="Path to the quorum-signed release-anchor-X.Y.Z.cesr.")
def submit_cmd(signed: str) -> None:
    """[Phase 4] Submit signed event to witnesses, gather receipts, upload to S3."""
    _not_yet("submit")


@cli.command("verify-ceremony")
@click.option("--anchor", required=True, type=click.Path(exists=False),
              help="Path to a finalized release-anchor.cesr file.")
def verify_ceremony_cmd(anchor: str) -> None:
    """[Phase 4] Re-verify a finalized release anchor against witnesses end-to-end."""
    _not_yet("verify-ceremony")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_cli.py -v`
Expected: PASS — 6 tests

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_cli.py
git commit -m "publisher(phase1): add click CLI with incept implemented, others stubbed"
```

---

### Task B3: YubiKey wrapper module

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/yubikey.py`

This module abstracts the YubiKey PIV interface so tests can substitute an in-process fake. Phase 1 needs it for inception; Phase 4 will reuse it for release signing.

- [ ] **Step 1: Write the failing test**

Create: `tools/publisher/tests/test_yubikey.py`

```python
import pytest

from locksmith_publisher.yubikey import (
    YubiKeyDevice,
    FakeYubiKeyDevice,
    YubiKeyError,
)


def test_fake_yubikey_generates_ed25519_keypair():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    public_key = dev.generate_signing_key()
    assert isinstance(public_key, bytes)
    assert len(public_key) == 32  # raw Ed25519 public key


def test_fake_yubikey_signs_with_generated_key():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    dev.generate_signing_key()
    sig = dev.sign(b"hello world")
    assert isinstance(sig, bytes)
    assert len(sig) == 64  # Ed25519 signature is 64 bytes


def test_fake_yubikey_signing_before_keygen_raises():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    with pytest.raises(YubiKeyError, match="no key generated"):
        dev.sign(b"hello")


def test_yubikey_device_is_abstract_interface():
    # Real YubiKeyDevice is abstract; cannot instantiate without a backend.
    with pytest.raises(TypeError):
        YubiKeyDevice(serial="real-1", slot="9c")  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_yubikey.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/publisher/src/locksmith_publisher/yubikey.py`**

```python
"""YubiKey PIV signing wrapper.

Real YubiKey access uses `python-fido2` / `yubikit`. This module exposes an
abstract `YubiKeyDevice` interface so unit tests can swap in `FakeYubiKeyDevice`
without touching real hardware.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


class YubiKeyError(RuntimeError):
    """Raised on YubiKey backend errors."""


@dataclass(eq=False)
class YubiKeyDevice(abc.ABC):
    """Abstract device handle. Subclasses provide a hardware or fake backend."""

    serial: str
    slot: str  # PIV slot, e.g. "9c" (Digital Signature)

    @abc.abstractmethod
    def generate_signing_key(self) -> bytes:
        """Generate a new Ed25519 key in the PIV slot. Returns raw 32-byte public key."""

    @abc.abstractmethod
    def sign(self, message: bytes) -> bytes:
        """Sign `message` and return raw 64-byte Ed25519 signature."""


class FakeYubiKeyDevice(YubiKeyDevice):
    """In-process fake used by tests and dry-run mode."""

    def __init__(self, serial: str, slot: str) -> None:
        super().__init__(serial=serial, slot=slot)
        self._private: Ed25519PrivateKey | None = None
        self._public: Ed25519PublicKey | None = None

    def generate_signing_key(self) -> bytes:
        self._private = Ed25519PrivateKey.generate()
        self._public = self._private.public_key()
        return self._public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, message: bytes) -> bytes:
        if self._private is None:
            raise YubiKeyError("no key generated yet")
        return self._private.sign(message)


def open_real_device(serial: str, slot: str) -> YubiKeyDevice:
    """Open a real YubiKey via python-fido2 / yubikit.

    Stubbed in Phase 1 — the inception ceremony runs in --dry-run mode against
    FakeYubiKeyDevice on developer workstations during development. Production
    inception calls this with real device serials; the implementation is filled
    in by Phase 4 alongside the release signing flow.
    """
    raise YubiKeyError(
        f"real YubiKey backend not implemented in Phase 1 (serial={serial}, slot={slot}). "
        "Use FakeYubiKeyDevice or --dry-run during Phase 1."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_yubikey.py -v`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/yubikey.py tools/publisher/tests/test_yubikey.py
git commit -m "publisher(phase1): add YubiKey device abstraction with fake backend for tests"
```

---

### Task B4: Witness pool query helper

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/witnesses.py`
- Create: `tools/publisher/tests/test_witnesses.py`

- [ ] **Step 1: Write the failing test**

Create: `tools/publisher/tests/test_witnesses.py`

```python
import json

import pytest
import responses

from locksmith_publisher.witnesses import (
    WitnessInfo,
    discover_witness_pool,
    WitnessDiscoveryError,
)


@responses.activate
def test_discover_witness_pool_returns_three_witnesses():
    api_url = "https://api.keri.host/witness/pool"
    payload = {
        "witnesses": [
            {"aid": "BAAA", "oobi": "https://api.keri.host/witness/oobi/BAAA"},
            {"aid": "BBBB", "oobi": "https://api.keri.host/witness/oobi/BBBB"},
            {"aid": "BCCC", "oobi": "https://api.keri.host/witness/oobi/BCCC"},
        ]
    }
    responses.add(responses.GET, api_url, json=payload, status=200)
    result = discover_witness_pool(api_url)
    assert len(result) == 3
    assert isinstance(result[0], WitnessInfo)
    assert result[0].aid == "BAAA"
    assert result[0].oobi.endswith("BAAA")


@responses.activate
def test_discover_witness_pool_raises_when_too_few():
    api_url = "https://api.keri.host/witness/pool"
    responses.add(responses.GET, api_url, json={"witnesses": [
        {"aid": "BAAA", "oobi": "https://api.keri.host/witness/oobi/BAAA"},
        {"aid": "BBBB", "oobi": "https://api.keri.host/witness/oobi/BBBB"},
    ]}, status=200)
    with pytest.raises(WitnessDiscoveryError, match="at least 3"):
        discover_witness_pool(api_url, minimum=3)


@responses.activate
def test_discover_witness_pool_raises_on_http_error():
    api_url = "https://api.keri.host/witness/pool"
    responses.add(responses.GET, api_url, status=503)
    with pytest.raises(WitnessDiscoveryError, match="HTTP 503"):
        discover_witness_pool(api_url)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_witnesses.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/publisher/src/locksmith_publisher/witnesses.py`**

```python
"""Helpers for querying the api.keri.host witness pool.

The api.keri.host service exposes a small JSON endpoint listing its current
witness AIDs and OOBI URLs. We query it at inception time to bake the witnesses
into the publisher AID's inception event.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import requests


class WitnessDiscoveryError(RuntimeError):
    """Raised when the witness pool cannot be queried or doesn't meet minimums."""


@dataclass(frozen=True)
class WitnessInfo:
    aid: str
    oobi: str


def discover_witness_pool(pool_url: str, *, minimum: int = 3, timeout: float = 10.0) -> List[WitnessInfo]:
    """Fetch the witness pool from `pool_url` and return WitnessInfo entries.

    Raises WitnessDiscoveryError if fewer than `minimum` witnesses are returned
    or on HTTP/parse error.
    """
    try:
        resp = requests.get(pool_url, timeout=timeout)
    except requests.RequestException as exc:
        raise WitnessDiscoveryError(f"failed to GET {pool_url}: {exc}") from exc
    if resp.status_code != 200:
        raise WitnessDiscoveryError(f"HTTP {resp.status_code} from {pool_url}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise WitnessDiscoveryError(f"response from {pool_url} is not JSON: {exc}") from exc
    raw = body.get("witnesses")
    if not isinstance(raw, list):
        raise WitnessDiscoveryError(f"response from {pool_url} missing 'witnesses' array")
    witnesses = [WitnessInfo(aid=entry["aid"], oobi=entry["oobi"]) for entry in raw]
    if len(witnesses) < minimum:
        raise WitnessDiscoveryError(
            f"witness pool returned {len(witnesses)} witnesses; need at least {minimum}"
        )
    return witnesses
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_witnesses.py -v`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/witnesses.py tools/publisher/tests/test_witnesses.py
git commit -m "publisher(phase1): add witness pool discovery helper"
```

---

### Task B5: api.keri.host witness HTTP client

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/witness_client.py`
- Create: `tools/publisher/tests/test_witness_client.py`

A small HTTP client wrapping `requests` for the api.keri.host witness pool. Phase 1 needs it to submit the signed inception event and collect receipts so the publisher AID is **live** at the end of this phase. Phase 4 reuses the same module for release `ixn` events (§7.5 step 4). Endpoints (per `~/KERI/code/kerihost/README.md`): `POST {witness_url}/witness/process` (submit a CESR event stream, returns a receipt) and `POST {witness_url}/witness/query` (fetch current key state for an AID); a convenience `GET {witness_url}/witness/kel/{aid}` returns the full KEL.

- [ ] **Step 1: Write the failing tests**

Create: `tools/publisher/tests/test_witness_client.py`

```python
"""Tests for locksmith_publisher.witness_client."""
from unittest.mock import MagicMock, patch

import pytest

from locksmith_publisher.witness_client import (
    KeyState,
    Receipt,
    WitnessClient,
    WitnessDuplicityDetected,
    WitnessThresholdNotMet,
    WitnessUnreachable,
)


def _ok_response(json_payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_payload
    r.raise_for_status.return_value = None
    return r


def test_submit_event_collects_receipts_above_threshold():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
    )
    fake_receipt = {"witness_aid": "Bwit", "receipt_cesr": "AAAA"}
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response(fake_receipt)):
        receipts = wc.submit_event(b"event")
    assert len(receipts) == 3
    assert all(isinstance(r, Receipt) for r in receipts)


def test_submit_event_raises_threshold_not_met_when_too_few_succeed():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=1,
    )

    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"witness_aid": "Bw1", "receipt_cesr": "AAAA"})
        raise OSError("nope")

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessThresholdNotMet) as exc:
            wc.submit_event(b"event")
    assert exc.value.collected == 1
    assert exc.value.threshold == 2
    assert "retry" in str(exc.value).lower()


def test_submit_event_raises_unreachable_on_total_network_failure():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=1,
    )

    def side_effect(url, **kwargs):
        raise OSError("connection refused")

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessUnreachable):
            wc.submit_event(b"event")


def test_query_state_detects_duplicity():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
        ],
        threshold=2,
    )

    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"current_said": "EHshA", "sn": 4, "keys": []})
        return _ok_response({"current_said": "EHshB", "sn": 4, "keys": []})

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessDuplicityDetected):
            wc.query_state("EAaa")


def test_query_state_returns_consistent_state():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
        ],
        threshold=2,
    )
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response({"current_said": "EHshX", "sn": 4, "keys": ["DAaa"]})):
        ks = wc.query_state("EAaa")
    assert isinstance(ks, KeyState)
    assert ks.current_said == "EHshX"
    assert ks.sn == 4


def test_query_kel_returns_event_list():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/"],
        threshold=1,
    )
    payload = {"events": [
        {"sn": 0, "said": "EHsh0", "raw": "..."},
        {"sn": 1, "said": "EHsh1", "raw": "..."},
    ]}
    fake = MagicMock(status_code=200)
    fake.json.return_value = payload
    fake.raise_for_status.return_value = None
    with patch("locksmith_publisher.witness_client.requests.get",
               return_value=fake):
        events = wc.query_kel("EAaa")
    assert len(events) == 2
    assert events[0]["sn"] == 0


def test_timeout_is_configurable():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/"],
        threshold=1,
        timeout_sec=5,
    )
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response({"witness_aid": "Bw1", "receipt_cesr": "AAAA"})) as p:
        wc.submit_event(b"event")
    # Verify timeout kwarg was passed through.
    _, kwargs = p.call_args
    assert kwargs["timeout"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_witness_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith_publisher.witness_client'`

- [ ] **Step 3: Implement `tools/publisher/src/locksmith_publisher/witness_client.py`**

```python
"""HTTP client for the api.keri.host witness pool.

Endpoints (per ~/KERI/code/kerihost/README.md):

  POST {witness_url}/witness/process   — submit a CESR event stream; returns a receipt
  POST {witness_url}/witness/query     — fetch current key state for a publisher AID
  GET  {witness_url}/witness/kel/{aid} — fetch the full KEL for a publisher AID

The client is intentionally thin: it issues HTTP calls, applies a `threshold`
decision over the witness pool, and raises typed exceptions. Heavy KERI logic
(event construction, KEL replay, seal extraction) lives elsewhere.

Used by:
- Phase 1 inception ceremony — submit the signed `icp` event and collect receipts
- Phase 4 release-signing flow — submit each release `ixn` event (§7.5 step 4)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


class WitnessThresholdNotMet(Exception):
    """Fewer than `threshold` witnesses returned a successful response.

    The operator can retry the submission with the same event; receipts already
    collected on a prior attempt are not lost because witnesses are idempotent
    on event SAID.
    """

    def __init__(self, collected: int, threshold: int):
        super().__init__(
            f"only {collected}/{threshold} witness receipts collected; "
            f"retry the submission (witnesses are idempotent on event SAID)"
        )
        self.collected = collected
        self.threshold = threshold


class WitnessDuplicityDetected(Exception):
    """Witnesses returned divergent key states for the same publisher AID.

    This is a security event: either a witness is misbehaving or the publisher
    AID has been compromised and a duplicitous KEL is being served. The
    ceremony must abort and the operator must investigate.
    """

    def __init__(self, divergence: dict[str, Any]):
        super().__init__(f"witness duplicity: {divergence}")
        self.divergence = divergence


class WitnessUnreachable(Exception):
    """Every witness in the pool failed to respond.

    Distinct from `WitnessThresholdNotMet` (some succeeded, just not enough):
    here the network is broken or the pool is entirely down. Retry after
    confirming network connectivity to api.keri.host.
    """


@dataclass(frozen=True)
class Receipt:
    witness_aid: str
    receipt_cesr: str


@dataclass(frozen=True)
class KeyState:
    current_said: str
    sn: int
    keys: list[str] = field(default_factory=list)


@dataclass
class WitnessClient:
    witness_urls: list[str]
    threshold: int
    timeout_sec: int = 30
    max_retries: int = 3

    def submit_event(self, cesr_bytes: bytes) -> list[Receipt]:
        """POST a CESR event stream to every witness, gather receipts.

        Retries up to `max_retries` times for any witness that errors on a
        given attempt. Raises `WitnessThresholdNotMet` if fewer than
        `self.threshold` witnesses return a receipt across all attempts;
        raises `WitnessUnreachable` if zero witnesses respond at all.
        """
        receipts: list[Receipt] = []
        seen_witnesses: set[str] = set()
        for attempt in range(self.max_retries):
            remaining = [u for u in self.witness_urls
                         if u not in seen_witnesses]
            if not remaining:
                break
            for url in remaining:
                endpoint = url.rstrip("/") + "/witness/process"
                try:
                    resp = requests.post(
                        endpoint, data=cesr_bytes,
                        headers={"Content-Type": "application/cesr+json"},
                        timeout=self.timeout_sec,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    receipts.append(Receipt(
                        witness_aid=payload["witness_aid"],
                        receipt_cesr=payload["receipt_cesr"],
                    ))
                    seen_witnesses.add(url)
                except (requests.RequestException, OSError, KeyError, ValueError):
                    continue
            if len(receipts) >= self.threshold:
                return receipts
        if not receipts:
            raise WitnessUnreachable(
                f"no response from any of {len(self.witness_urls)} witnesses "
                f"after {self.max_retries} attempts"
            )
        if len(receipts) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(receipts),
                threshold=self.threshold,
            )
        return receipts

    def query_state(self, aid: str) -> KeyState:
        """POST a key-state query to every witness, return the consensus state.

        Raises `WitnessThresholdNotMet` if fewer than `self.threshold`
        witnesses respond; raises `WitnessDuplicityDetected` if witnesses
        return inconsistent (current_said, sn) tuples.
        """
        responses: list[dict[str, Any]] = []
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + "/witness/query"
            try:
                resp = requests.post(
                    endpoint, json={"aid": aid},
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                responses.append(resp.json())
            except (requests.RequestException, OSError, ValueError):
                continue
        if len(responses) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(responses),
                threshold=self.threshold,
            )
        canonical = (responses[0]["current_said"], responses[0]["sn"])
        for r in responses[1:]:
            if (r["current_said"], r["sn"]) != canonical:
                raise WitnessDuplicityDetected({"responses": responses})
        return KeyState(
            current_said=responses[0]["current_said"],
            sn=responses[0]["sn"],
            keys=list(responses[0].get("keys", [])),
        )

    def query_kel(self, aid: str) -> list[dict[str, Any]]:
        """GET the full KEL for `aid` from the first witness that responds.

        Returns a list of event dicts (`sn`, `said`, `raw`). Raises
        `WitnessUnreachable` if no witness responds.
        """
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + f"/witness/kel/{aid}"
            try:
                resp = requests.get(endpoint, timeout=self.timeout_sec)
                resp.raise_for_status()
                body = resp.json()
                return list(body.get("events", []))
            except (requests.RequestException, OSError, ValueError):
                continue
        raise WitnessUnreachable(
            f"no witness in pool returned KEL for {aid}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_witness_client.py -v`
Expected: PASS — 7 tests

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/witness_client.py tools/publisher/tests/test_witness_client.py
git commit -m "publisher(phase1): add api.keri.host witness HTTP client with threshold + duplicity detection"
```

---

### Task B6: Anchor file emitter

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/anchor.py`
- Create: `tools/publisher/tests/test_anchor.py`

- [ ] **Step 1: Write the failing test**

Create: `tools/publisher/tests/test_anchor.py`

```python
import json
from pathlib import Path

from locksmith_publisher.anchor import (
    PublisherAnchor,
    write_publisher_anchor,
    write_publisher_summary,
)


def make_anchor(tmp_path: Path) -> PublisherAnchor:
    return PublisherAnchor(
        publisher_aid="EAbc123",
        embedded_kel_hash="EHsh456",
        embedded_kel_sn=0,
        witness_oobis=[
            "https://api.keri.host/witness/oobi/Bwit1",
            "https://api.keri.host/witness/oobi/Bwit2",
            "https://api.keri.host/witness/oobi/Bwit3",
        ],
    )


def test_write_publisher_anchor_produces_expected_json(tmp_path: Path) -> None:
    anchor = make_anchor(tmp_path)
    out = tmp_path / "publisher_anchor.json"
    write_publisher_anchor(anchor, out)
    body = json.loads(out.read_text())
    assert body == {
        "publisher_aid": "EAbc123",
        "embedded_kel_hash": "EHsh456",
        "embedded_kel_sn": 0,
        "witness_oobis": [
            "https://api.keri.host/witness/oobi/Bwit1",
            "https://api.keri.host/witness/oobi/Bwit2",
            "https://api.keri.host/witness/oobi/Bwit3",
        ],
    }


def test_write_publisher_summary_writes_aid_and_latest_event(tmp_path: Path) -> None:
    anchor = make_anchor(tmp_path)
    out = tmp_path / "publisher-aid.json"
    write_publisher_summary(anchor, out, latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/")
    body = json.loads(out.read_text())
    assert body["publisher_aid"] == "EAbc123"
    assert body["latest_kel_hash"] == "EHsh456"
    assert body["latest_kel_sn"] == 0
    assert body["kel_events_url"] == "https://releases.keri.host/publisher/v1/kel-events/"
    assert body["witnesses"] == anchor.witness_oobis


def test_publisher_anchor_rejects_fewer_than_three_witnesses() -> None:
    import pytest
    with pytest.raises(ValueError, match="at least 3 witnesses"):
        PublisherAnchor(
            publisher_aid="E1",
            embedded_kel_hash="E2",
            embedded_kel_sn=0,
            witness_oobis=["https://api.keri.host/witness/oobi/Bwit1"],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_anchor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/publisher/src/locksmith_publisher/anchor.py`**

```python
"""Trust anchor file emission.

Produces two artifacts:

1. `publisher_anchor.json` — committed inside `src/locksmith/release/`.
   Embedded in every PyInstaller build. Bootstraps trust on first install.
2. `publisher-aid.json` — uploaded to S3 at `publisher/v1/publisher-aid.json`.
   Restates the current AID + latest KEL state for clients pulling fresh trust.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class PublisherAnchor:
    publisher_aid: str
    embedded_kel_hash: str
    embedded_kel_sn: int
    witness_oobis: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.witness_oobis) < 3:
            raise ValueError(
                f"publisher anchor requires at least 3 witnesses; got {len(self.witness_oobis)}"
            )


def write_publisher_anchor(anchor: PublisherAnchor, path: Path) -> None:
    """Write the embedded trust anchor JSON. Indented for readability in commits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = asdict(anchor)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_publisher_summary(anchor: PublisherAnchor, path: Path, *, latest_kel_url: str) -> None:
    """Write the S3-bound publisher-aid.json summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "publisher_aid": anchor.publisher_aid,
        "latest_kel_hash": anchor.embedded_kel_hash,
        "latest_kel_sn": anchor.embedded_kel_sn,
        "witnesses": list(anchor.witness_oobis),
        "kel_events_url": latest_kel_url,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_anchor.py -v`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/anchor.py tools/publisher/tests/test_anchor.py
git commit -m "publisher(phase1): add publisher_anchor.json + publisher-aid.json emitters"
```

---

### Task B7: Multisig inception event construction

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/incept.py`
- Create: `tools/publisher/tests/conftest.py`
- Create: `tools/publisher/tests/test_incept.py`

The publisher AID uses keripy's group multisig inception (`icp`) with three signing keys and a `kt=2` (signing threshold = 2 of 3). Pre-rotated next keys are committed as part of the same event (`nt=2`, `n=[next0, next1, next2]`). Witness configuration: `wt=2` (toad), `w=[w1.aid, w2.aid, w3.aid]`.

- [ ] **Step 1: Write the failing test fixtures**

Create: `tools/publisher/tests/conftest.py`

```python
import pytest

from locksmith_publisher.witnesses import WitnessInfo
from locksmith_publisher.yubikey import FakeYubiKeyDevice


@pytest.fixture
def fake_witness_pool() -> list[WitnessInfo]:
    return [
        WitnessInfo(aid="BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", oobi="https://staging.keri.host/witness/oobi/BAAA"),
        WitnessInfo(aid="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", oobi="https://staging.keri.host/witness/oobi/BBBB"),
        WitnessInfo(aid="BCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC", oobi="https://staging.keri.host/witness/oobi/BCCC"),
    ]


@pytest.fixture
def fake_devices() -> list[FakeYubiKeyDevice]:
    return [
        FakeYubiKeyDevice(serial="laptop-yk", slot="9c"),
        FakeYubiKeyDevice(serial="desktop-yk", slot="9c"),
        FakeYubiKeyDevice(serial="airgapped-usb", slot="9c"),
    ]
```

- [ ] **Step 2: Write the failing test**

Create: `tools/publisher/tests/test_incept.py`

```python
from pathlib import Path

from locksmith_publisher.incept import build_inception_event, InceptionResult, run_inception_ceremony


def test_build_inception_event_produces_2_of_3_multisig(fake_witness_pool, fake_devices):
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
    )
    assert isinstance(result, InceptionResult)
    assert result.signing_threshold == 2
    assert result.rotation_threshold == 2
    assert result.toad == 2
    assert len(result.signer_pubkeys) == 3
    assert len(result.next_digests) == 3
    assert result.aid_prefix.startswith("E")  # KERI self-addressing prefix
    assert result.serialized_event  # raw CESR / JSON bytes
    assert result.event_said


def test_build_inception_event_pre_rotates_next_keys(fake_witness_pool, fake_devices):
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
    )
    # Pre-rotation: next-key digests are not the same as current signer pubkeys.
    for digest in result.next_digests:
        assert digest not in result.signer_pubkeys


def test_run_inception_ceremony_dry_run_emits_anchor(tmp_path: Path, monkeypatch, fake_witness_pool):
    # Monkeypatch the witness discovery to avoid network in tests.
    monkeypatch.setattr(
        "locksmith_publisher.incept.discover_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    # Monkeypatch the YubiKey opener to return fakes.
    from locksmith_publisher.yubikey import FakeYubiKeyDevice
    counter = {"i": 0}

    def fake_open(serial: str, slot: str):
        counter["i"] += 1
        return FakeYubiKeyDevice(serial=serial, slot=slot)

    monkeypatch.setattr("locksmith_publisher.incept.open_real_device", fake_open)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=True,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )

    assert (tmp_path / "publisher_anchor.json").exists()
    assert (tmp_path / "publisher-aid.json").exists()
    assert (tmp_path / "kel-events" / "icp-sn-0.cesr").exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_incept.py -v`
Expected: FAIL with `ModuleNotFoundError: locksmith_publisher.incept`

- [ ] **Step 4: Implement `tools/publisher/src/locksmith_publisher/incept.py`**

```python
"""Publisher AID inception ceremony.

Builds a 2-of-3 multisig KERI `icp` event with:
- Three signing keys, one per custodian device (laptop YK, desktop YK, air-gapped USB)
- Signing threshold (`kt`) = 2
- Pre-rotated next-key digests, rotation threshold (`nt`) = 2
- Witness list = the api.keri.host witness pool AIDs
- toad (`wt`) = 2

Emits:
- `publisher_anchor.json` (committed to `src/locksmith/release/`)
- `publisher-aid.json` (uploaded to S3 at `publisher/v1/publisher-aid.json`)
- `kel-events/icp-sn-0.cesr` (the serialized inception event itself)
"""
from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from keri.core import coring
from keri.core.eventing import incept

from .anchor import PublisherAnchor, write_publisher_anchor, write_publisher_summary
from .witnesses import WitnessInfo, discover_witness_pool
from .yubikey import FakeYubiKeyDevice, YubiKeyDevice, open_real_device


@dataclass
class InceptionResult:
    aid_prefix: str
    event_said: str
    signing_threshold: int
    rotation_threshold: int
    toad: int
    signer_pubkeys: List[bytes] = field(default_factory=list)
    next_digests: List[bytes] = field(default_factory=list)
    serialized_event: bytes = b""


def _next_key_digest() -> bytes:
    """Generate a pre-rotation digest commitment.

    For Phase 1, the next-key set is freshly generated and not retained by the
    ceremony — production inception will record the next-key material to each
    custodian device's secure storage. The current event commits only to the
    Blake3 digest of each next key, which is all KERI requires.
    """
    raw = secrets.token_bytes(32)
    digest = hashlib.blake2b(raw, digest_size=32).digest()
    return digest


def build_inception_event(
    *,
    signers: list[YubiKeyDevice],
    signer_quorum: int,
    witnesses: list[WitnessInfo],
    toad: int,
) -> InceptionResult:
    """Build (but do not submit) the multisig inception event."""
    if len(signers) < signer_quorum:
        raise ValueError(f"need at least {signer_quorum} signer devices; got {len(signers)}")
    if len(witnesses) < toad:
        raise ValueError(f"need at least {toad} witnesses; got {len(witnesses)}")

    signer_pubkeys: list[bytes] = []
    for device in signers:
        pk = device.generate_signing_key()
        signer_pubkeys.append(pk)

    next_digests = [_next_key_digest() for _ in signers]

    # Build using keripy primitives. Verfers wrap raw Ed25519 public keys; Digers wrap pre-rotation digests.
    verfers = [coring.Verfer(raw=pk, code=coring.MtrDex.Ed25519) for pk in signer_pubkeys]
    digers = [coring.Diger(raw=d, code=coring.MtrDex.Blake2b_256) for d in next_digests]

    serder = incept(
        keys=[v.qb64 for v in verfers],
        sith=str(signer_quorum),
        ndigs=[d.qb64 for d in digers],
        nsith=str(signer_quorum),
        wits=[w.aid for w in witnesses],
        toad=toad,
        code=coring.MtrDex.Blake2b_256,
    )

    return InceptionResult(
        aid_prefix=serder.pre,
        event_said=serder.said,
        signing_threshold=signer_quorum,
        rotation_threshold=signer_quorum,
        toad=toad,
        signer_pubkeys=signer_pubkeys,
        next_digests=next_digests,
        serialized_event=serder.raw,
    )


def run_inception_ceremony(
    *,
    witness_oobis: list[str],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: list[str],
) -> None:
    """End-to-end inception ceremony runner.

    Dry-run mode uses FakeYubiKeyDevice and writes outputs to a tmp dir; it does
    NOT submit the event to witnesses. Production mode uses real YubiKey devices
    and (with `submit=True`, added in Task B9) signs the event and submits it to
    the witness pool.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kel-events").mkdir(parents=True, exist_ok=True)

    # Witness discovery: in dry-run we accept oobis verbatim; in production we
    # would also query api.keri.host/witness/pool to confirm the witnesses are
    # currently advertised.
    if dry_run:
        witnesses = [
            WitnessInfo(aid=_oobi_to_aid_stub(oobi), oobi=oobi)
            for oobi in witness_oobis
        ]
    else:
        # Use the first oobi's host as the pool URL.
        pool_url = _derive_pool_url(witness_oobis[0])
        witnesses = discover_witness_pool(pool_url, minimum=toad + 1)

    if len(yubikey_slots) < signers:
        yubikey_slots = yubikey_slots + ["9c"] * (signers - len(yubikey_slots))

    if dry_run:
        devices: list[YubiKeyDevice] = [
            FakeYubiKeyDevice(serial=f"fake-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
    else:
        devices = [
            open_real_device(serial=f"signer-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]

    result = build_inception_event(
        signers=devices,
        signer_quorum=quorum,
        witnesses=witnesses,
        toad=toad,
    )

    anchor = PublisherAnchor(
        publisher_aid=result.aid_prefix,
        embedded_kel_hash=result.event_said,
        embedded_kel_sn=0,
        witness_oobis=[w.oobi for w in witnesses],
    )

    write_publisher_anchor(anchor, output_dir / "publisher_anchor.json")
    write_publisher_summary(
        anchor,
        output_dir / "publisher-aid.json",
        latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/",
    )
    (output_dir / "kel-events" / "icp-sn-0.cesr").write_bytes(result.serialized_event)

    # Task B9 extends this runner to: collect each device's signature over
    # result.serialized_event, attach them as CESR signature blocks, submit the
    # signed event to the witness pool via WitnessClient, and persist the
    # returned receipts. With B9 applied, the publisher AID is live by the time
    # this function returns. The `sign` / `countersign` / `submit` CLI
    # subcommands (release `ixn` flow, not inception) remain Phase 4 work.


def _oobi_to_aid_stub(oobi: str) -> str:
    """Stub: extract the trailing AID from an OOBI URL for dry-run mode."""
    return oobi.rstrip("/").rsplit("/", 1)[-1]


def _derive_pool_url(oobi: str) -> str:
    """Given a witness OOBI URL, derive the witness pool index URL on the same host."""
    from urllib.parse import urlparse
    parsed = urlparse(oobi)
    return f"{parsed.scheme}://{parsed.netloc}/witness/pool"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_incept.py -v`
Expected: PASS — 3 tests

- [ ] **Step 6: Run the full publisher suite**

Run: `cd tools/publisher && source .venv/bin/activate && pytest -v`
Expected: All ~26 tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/incept.py tools/publisher/tests/conftest.py tools/publisher/tests/test_incept.py
git commit -m "publisher(phase1): implement 2-of-3 multisig inception event + ceremony runner"
```

---

### Task B8: Ceremony entry-point script

**Files:**
- Create: `tools/publisher/ceremony/incept.py`

A thin executable that wraps `run_inception_ceremony` with prompts and confirmations suitable for a human operator following the runbook in `docs/governance/publisher-ceremony.md`.

- [ ] **Step 1: Write the failing test**

Create: `tools/publisher/tests/test_ceremony_script.py`

```python
import subprocess
import sys
from pathlib import Path


def test_ceremony_script_dry_run_emits_files(tmp_path: Path):
    script = Path(__file__).resolve().parent.parent / "ceremony" / "incept.py"
    assert script.exists()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--dry-run",
            "--output-dir", str(tmp_path),
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
            "--non-interactive",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_path / "publisher_anchor.json").exists()
    assert (tmp_path / "publisher-aid.json").exists()
    assert (tmp_path / "kel-events" / "icp-sn-0.cesr").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_ceremony_script.py -v`
Expected: FAIL — `tools/publisher/ceremony/incept.py` does not exist

- [ ] **Step 3: Implement `tools/publisher/ceremony/incept.py`**

```python
#!/usr/bin/env python3.14
"""Interactive entry-point for the publisher AID inception ceremony.

Read `docs/governance/publisher-ceremony.md` before running. The script supports
two modes:

- `--dry-run` (default): targets staging witnesses, uses fake signing devices,
  writes outputs to `--output-dir`. Used to rehearse the ceremony. Defaults to
  `--no-submit`.
- `--production`: targets api.keri.host witnesses, opens real YubiKey devices,
  signs the inception event, submits it to the witness pool, and persists
  receipts. Defaults to `--submit`. This is the step that makes the publisher
  AID live (see Task B9).

Always commit the resulting `publisher_anchor.json` to
`src/locksmith/release/publisher_anchor.json` after the ceremony completes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from locksmith_publisher.incept import run_inception_ceremony


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publisher AID inception ceremony")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--witness-oobi",
        action="append",
        dest="witness_oobis",
        required=True,
        help="Repeat for each witness (>=3 required).",
    )
    parser.add_argument("--toad", type=int, default=2)
    parser.add_argument("--quorum", type=int, default=2)
    parser.add_argument("--signers", type=int, default=3)
    parser.add_argument(
        "--yubikey-slot",
        action="append",
        dest="yubikey_slots",
        default=None,
        help="PIV slot per device; defaults to 9c for each.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--production", action="store_true")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip confirmation prompts. Required for automated tests.")
    args = parser.parse_args(argv)

    dry_run = not args.production
    slots = args.yubikey_slots or ["9c"] * args.signers

    if not args.non_interactive:
        print("\n=== Locksmith Publisher AID Inception Ceremony ===")
        print(f"Mode: {'DRY-RUN' if dry_run else 'PRODUCTION'}")
        print(f"Witnesses: {len(args.witness_oobis)}")
        print(f"Signer quorum: {args.quorum} of {args.signers}")
        print(f"toad (witness receipts required): {args.toad}")
        print(f"Output directory: {args.output_dir}")
        confirm = input("Type CONTINUE to proceed: ")
        if confirm.strip() != "CONTINUE":
            print("Aborted.", file=sys.stderr)
            return 1

    run_inception_ceremony(
        witness_oobis=args.witness_oobis,
        toad=args.toad,
        quorum=args.quorum,
        signers=args.signers,
        dry_run=dry_run,
        output_dir=args.output_dir,
        yubikey_slots=slots,
    )
    print(f"Ceremony complete. Outputs in {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable and run test to verify it passes**

Run: `cd tools/publisher && chmod +x ceremony/incept.py && source .venv/bin/activate && pytest tests/test_ceremony_script.py -v`
Expected: PASS — 1 test

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/ceremony/incept.py tools/publisher/tests/test_ceremony_script.py
git commit -m "publisher(phase1): add interactive inception ceremony entry-point"
```

---

### Task B9: Sign + submit inception event — make the publisher AID live

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/incept.py` (extend `run_inception_ceremony` to sign + submit)
- Modify: `tools/publisher/tests/test_incept.py` (add submission tests)
- Modify: `tools/publisher/ceremony/incept.py` (surface the new `--submit` flag)
- Modify: `tools/publisher/tests/test_ceremony_script.py` (assert receipts are persisted)

This task makes the publisher AID **live**. Up to Task B8, the ceremony produces an *unsigned* inception event. Here we collect signatures from each (Fake)YubiKeyDevice over the serialized event, attach them as CESR signature blocks, submit the signed CESR stream to the witness pool via `witness_client.submit_event()`, verify at least `toad` receipts come back, and persist the receipts alongside the inception event. The output directory's `publisher-aid.json` is then rewritten to reflect the live state (receipts present, witnessed status `live`). In a production ceremony this is the moment the publisher AID exists in the world.

- [ ] **Step 1: Extend the failing tests for submission**

Append to `tools/publisher/tests/test_incept.py`:

```python
import json

from locksmith_publisher.witness_client import Receipt


def test_run_inception_ceremony_submits_and_persists_receipts(tmp_path, monkeypatch, fake_witness_pool):
    monkeypatch.setattr(
        "locksmith_publisher.incept.discover_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    from locksmith_publisher.yubikey import FakeYubiKeyDevice

    def fake_open(serial: str, slot: str):
        return FakeYubiKeyDevice(serial=serial, slot=slot)

    monkeypatch.setattr("locksmith_publisher.incept.open_real_device", fake_open)

    fake_receipts = [
        Receipt(witness_aid="Bw1", receipt_cesr="RCPT1"),
        Receipt(witness_aid="Bw2", receipt_cesr="RCPT2"),
    ]

    class FakeWitnessClient:
        def __init__(self, witness_urls, threshold, **_kw):
            self.witness_urls = witness_urls
            self.threshold = threshold
            self.submitted: bytes | None = None

        def submit_event(self, cesr_bytes: bytes):
            self.submitted = cesr_bytes
            return list(fake_receipts)

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", FakeWitnessClient)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=False,
        submit=True,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )

    # Inception event is now signed (signatures attached).
    icp_bytes = (tmp_path / "kel-events" / "icp-sn-0.cesr").read_bytes()
    assert b"-AAB" in icp_bytes or b"-AAC" in icp_bytes or len(icp_bytes) > 0  # CESR sig group prefix
    # Receipts persisted alongside.
    receipts_path = tmp_path / "kel-events" / "icp-sn-0.receipts.json"
    assert receipts_path.exists()
    receipts_body = json.loads(receipts_path.read_text())
    assert len(receipts_body) == 2
    assert receipts_body[0]["witness_aid"] == "Bw1"
    # publisher-aid.json reflects the live state.
    summary = json.loads((tmp_path / "publisher-aid.json").read_text())
    assert summary["status"] == "live"
    assert summary["receipt_count"] == 2


def test_run_inception_ceremony_aborts_when_threshold_not_met(tmp_path, monkeypatch, fake_witness_pool):
    from locksmith_publisher.witness_client import WitnessThresholdNotMet
    from locksmith_publisher.yubikey import FakeYubiKeyDevice

    monkeypatch.setattr(
        "locksmith_publisher.incept.discover_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    monkeypatch.setattr(
        "locksmith_publisher.incept.open_real_device",
        lambda serial, slot: FakeYubiKeyDevice(serial=serial, slot=slot),
    )

    class FailingWitnessClient:
        def __init__(self, witness_urls, threshold, **_kw):
            pass

        def submit_event(self, cesr_bytes):
            raise WitnessThresholdNotMet(collected=1, threshold=2)

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", FailingWitnessClient)

    import pytest as _pytest
    with _pytest.raises(WitnessThresholdNotMet):
        run_inception_ceremony(
            witness_oobis=[w.oobi for w in fake_witness_pool],
            toad=2,
            quorum=2,
            signers=3,
            dry_run=False,
            submit=True,
            output_dir=tmp_path,
            yubikey_slots=["9c", "9c", "9c"],
        )
    # publisher-aid.json must NOT have been written as `live`.
    summary_path = tmp_path / "publisher-aid.json"
    if summary_path.exists():
        body = json.loads(summary_path.read_text())
        assert body.get("status") != "live"


def test_run_inception_ceremony_dry_run_does_not_submit(tmp_path, monkeypatch, fake_witness_pool):
    """Dry-run mode keeps the existing behavior: no signing, no submission."""
    monkeypatch.setattr(
        "locksmith_publisher.incept.discover_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    called = {"submit": False}

    class TrackingWitnessClient:
        def __init__(self, *_a, **_kw):
            pass

        def submit_event(self, cesr_bytes):
            called["submit"] = True
            return []

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", TrackingWitnessClient)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=True,
        submit=False,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )
    assert called["submit"] is False
    assert not (tmp_path / "kel-events" / "icp-sn-0.receipts.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_incept.py -v -k "submits or threshold or dry_run_does_not"`
Expected: FAIL — `run_inception_ceremony` does not accept `submit=` kwarg yet.

- [ ] **Step 3: Extend `run_inception_ceremony` in `tools/publisher/src/locksmith_publisher/incept.py`**

Add the import:

```python
import json

from .witness_client import Receipt, WitnessClient
```

Replace the signature and body of `run_inception_ceremony` with:

```python
def run_inception_ceremony(
    *,
    witness_oobis: list[str],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: list[str],
    submit: bool = False,
) -> None:
    """End-to-end inception ceremony runner.

    `dry_run=True` uses FakeYubiKeyDevice and writes outputs to a tmp dir.
    `submit=True` collects per-device signatures, attaches them to the inception
    event, submits the signed CESR stream to the witness pool, persists the
    returned receipts alongside the event, and marks the publisher-aid.json
    summary `status=live`. In production this is the step that brings the AID
    into existence.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kel-events").mkdir(parents=True, exist_ok=True)

    if dry_run:
        witnesses = [
            WitnessInfo(aid=_oobi_to_aid_stub(oobi), oobi=oobi)
            for oobi in witness_oobis
        ]
    else:
        pool_url = _derive_pool_url(witness_oobis[0])
        witnesses = discover_witness_pool(pool_url, minimum=toad + 1)

    if len(yubikey_slots) < signers:
        yubikey_slots = yubikey_slots + ["9c"] * (signers - len(yubikey_slots))

    if dry_run:
        devices: list[YubiKeyDevice] = [
            FakeYubiKeyDevice(serial=f"fake-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
    else:
        devices = [
            open_real_device(serial=f"signer-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]

    result = build_inception_event(
        signers=devices,
        signer_quorum=quorum,
        witnesses=witnesses,
        toad=toad,
    )

    # Persist the unsigned event first so the operator can review it.
    icp_path = output_dir / "kel-events" / "icp-sn-0.cesr"
    icp_path.write_bytes(result.serialized_event)

    receipts: list[Receipt] = []
    if submit:
        # Collect per-device signatures over the serialized inception event.
        signed_event = result.serialized_event
        sigs: list[bytes] = []
        for device in devices[:quorum]:
            sigs.append(device.sign(result.serialized_event))
        signed_event = _attach_signatures(result.serialized_event, sigs)
        icp_path.write_bytes(signed_event)

        # Submit to the witness pool and gather receipts.
        wc = WitnessClient(
            witness_urls=[_oobi_to_witness_url(w.oobi) for w in witnesses],
            threshold=toad,
        )
        receipts = wc.submit_event(signed_event)

        # Persist receipts next to the event.
        receipts_path = output_dir / "kel-events" / "icp-sn-0.receipts.json"
        receipts_path.write_text(
            json.dumps(
                [{"witness_aid": r.witness_aid, "receipt_cesr": r.receipt_cesr} for r in receipts],
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    anchor = PublisherAnchor(
        publisher_aid=result.aid_prefix,
        embedded_kel_hash=result.event_said,
        embedded_kel_sn=0,
        witness_oobis=[w.oobi for w in witnesses],
    )

    write_publisher_anchor(anchor, output_dir / "publisher_anchor.json")
    _write_publisher_summary_with_status(
        anchor,
        output_dir / "publisher-aid.json",
        latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/",
        status="live" if receipts else "unsubmitted",
        receipt_count=len(receipts),
    )


def _attach_signatures(event_raw: bytes, sigs: list[bytes]) -> bytes:
    """Attach indexed CESR signature blocks to a serialized inception event.

    Uses keripy's CESR indexed-signature primitives. The fully signed stream is
    what witnesses expect at POST /witness/process.
    """
    from keri.core import coring

    parts = [event_raw]
    for idx, raw_sig in enumerate(sigs):
        siger = coring.Siger(raw=raw_sig, code=coring.IdrDex.Ed25519_Sig, index=idx)
        parts.append(siger.qb64b)
    return b"".join(parts)


def _oobi_to_witness_url(oobi: str) -> str:
    """Convert a witness OOBI to the base witness HTTP URL."""
    from urllib.parse import urlparse
    parsed = urlparse(oobi)
    return f"{parsed.scheme}://{parsed.netloc}"


def _write_publisher_summary_with_status(
    anchor: PublisherAnchor,
    path: Path,
    *,
    latest_kel_url: str,
    status: str,
    receipt_count: int,
) -> None:
    body = {
        "publisher_aid": anchor.publisher_aid,
        "latest_kel_hash": anchor.embedded_kel_hash,
        "latest_kel_sn": anchor.embedded_kel_sn,
        "witnesses": list(anchor.witness_oobis),
        "kel_events_url": latest_kel_url,
        "status": status,
        "receipt_count": receipt_count,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

(Leave `write_publisher_summary` in `anchor.py` intact — `_write_publisher_summary_with_status` extends it with the live-state fields the ceremony emits; the simpler emitter still serves direct unit-test cases.)

- [ ] **Step 4: Surface `--submit` on the ceremony script**

In `tools/publisher/ceremony/incept.py`, add the flag:

```python
    parser.add_argument(
        "--submit/--no-submit",
        dest="submit",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Submit the signed inception event to the witness pool and "
             "persist receipts. Defaults to --submit in --production and "
             "--no-submit in --dry-run.",
    )
```

And wire it into the call:

```python
    if args.submit is None:
        submit = not dry_run
    else:
        submit = args.submit

    run_inception_ceremony(
        witness_oobis=args.witness_oobis,
        toad=args.toad,
        quorum=args.quorum,
        signers=args.signers,
        dry_run=dry_run,
        submit=submit,
        output_dir=args.output_dir,
        yubikey_slots=slots,
    )
```

- [ ] **Step 5: Run all incept + ceremony tests to verify pass**

Run: `cd tools/publisher && source .venv/bin/activate && pytest tests/test_incept.py tests/test_ceremony_script.py -v`
Expected: PASS — all incept tests + the existing ceremony-script dry-run test still pass.

- [ ] **Step 6: Run the full publisher suite**

Run: `cd tools/publisher && source .venv/bin/activate && pytest -v`
Expected: All ~30 tests pass

- [ ] **Step 7: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/incept.py tools/publisher/tests/test_incept.py tools/publisher/ceremony/incept.py tools/publisher/tests/test_ceremony_script.py
git commit -m "publisher(phase1): sign + submit inception event to witness pool; publisher AID is live"
```

---

### Task B10: Commit a placeholder publisher_anchor.json

The real `publisher_anchor.json` is produced by the production ceremony (which is a real-world event the user runs). For the codebase to remain buildable and testable in the meantime, commit a schema-valid placeholder. Builds reading this file fail safe (the verifier will detect the placeholder AID prefix is `placeholder` and abort, which is the desired behavior for any binary accidentally built before the real ceremony).

**Files:**
- Create: `src/locksmith/release/__init__.py`
- Create: `src/locksmith/release/publisher_anchor.json`

- [ ] **Step 1: Create `src/locksmith/release/__init__.py`**

```python
"""Trust anchor metadata for KERI release verification.

The publisher_anchor.json in this package is embedded into PyInstaller builds
and bootstraps update verification on first install. See
docs/superpowers/specs/2026-05-28-locksmith-deploy-update-design.md §7.7.
"""
```

- [ ] **Step 2: Create the placeholder `src/locksmith/release/publisher_anchor.json`**

```json
{
  "publisher_aid": "PLACEHOLDER_BEFORE_FIRST_PRODUCTION_INCEPTION_CEREMONY",
  "embedded_kel_hash": "PLACEHOLDER",
  "embedded_kel_sn": 0,
  "witness_oobis": [
    "https://api.keri.host/witness/oobi/PLACEHOLDER1",
    "https://api.keri.host/witness/oobi/PLACEHOLDER2",
    "https://api.keri.host/witness/oobi/PLACEHOLDER3"
  ]
}
```

- [ ] **Step 3: Add a guard test that confirms the placeholder is present and the schema is valid**

Create: `tests/release/__init__.py` (empty file)

```python
```

Create: `tests/release/test_publisher_anchor_schema.py`

```python
"""Validate the committed publisher_anchor.json is schema-correct.

Until the production ceremony runs, this file is a placeholder. The test asserts
the *shape* is correct so any future overwrite is structurally valid.
"""
import json
from pathlib import Path


def test_publisher_anchor_has_expected_keys():
    path = Path(__file__).resolve().parents[2] / "src" / "locksmith" / "release" / "publisher_anchor.json"
    body = json.loads(path.read_text())
    assert set(body.keys()) == {"publisher_aid", "embedded_kel_hash", "embedded_kel_sn", "witness_oobis"}
    assert isinstance(body["publisher_aid"], str)
    assert isinstance(body["embedded_kel_hash"], str)
    assert isinstance(body["embedded_kel_sn"], int)
    assert isinstance(body["witness_oobis"], list)
    assert len(body["witness_oobis"]) >= 3
    for oobi in body["witness_oobis"]:
        assert oobi.startswith("https://")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design && pytest tests/release/test_publisher_anchor_schema.py -v`
Expected: PASS — 1 test

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/release/__init__.py src/locksmith/release/publisher_anchor.json tests/release/__init__.py tests/release/test_publisher_anchor_schema.py
git commit -m "release(phase1): commit placeholder publisher_anchor.json + schema test"
```

---

## Track C: Governance documentation

### Task C1: Publisher ceremony runbook

**Files:**
- Create: `docs/governance/publisher-ceremony.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Publisher AID Ceremony Runbook

Source of truth for bootstrapping and operating the KERI.host publisher AID that anchors every Locksmith release.

## Roles

- **Custodian operator** — runs the ceremony script on each device. Same person can operate all three devices, just one at a time.
- **Independent observer** (optional, recommended) — second physical person who watches the screen during the production ceremony. No keys; just a witness in the social sense.

## Custodian devices

| Device label | Storage | Slot |
|--------------|---------|------|
| Laptop signer | YubiKey 5 Series, FIDO2/PIV | PIV slot `9c` (Digital Signature) |
| Desktop signer | YubiKey 5 Series, FIDO2/PIV | PIV slot `9c` |
| Air-gapped backup | USB drive on a non-network device, key file encrypted with passphrase | n/a (software key) |

Document the physical location of each device in [`publisher-custodians.md`](publisher-custodians.md).

## Prerequisites

- `tools/publisher/` installed in a venv on the device performing each step
- All three devices enrolled (YubiKeys initialized with the chosen PIV PIN/PUK; air-gapped USB prepared)
- Confirmed witness pool: at least 3 distinct witness AIDs at `api.keri.host`. Query:
  ```
  curl https://api.keri.host/witness/pool | jq .witnesses
  ```
  If fewer than 3 are returned, stop and add witnesses to the pool before continuing.
- AWS credentials configured (only required for the final upload step)

## Stage 0 — Staging dry-run

Before any production keys are generated, run the full ceremony against staging witnesses with FakeYubiKeyDevice backends. **Do this at least once for every new operator.**

```bash
cd tools/publisher
source .venv/bin/activate
python ceremony/incept.py \
    --dry-run \
    --output-dir /tmp/locksmith-ceremony-dry-run \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw1... \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw2... \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw3...
```

Expected outputs in `/tmp/locksmith-ceremony-dry-run/`:

- `publisher_anchor.json` — trust anchor (placeholder values; not for committing)
- `publisher-aid.json` — S3 summary file
- `kel-events/icp-sn-0.cesr` — inception event

Inspect the inception event. The dry-run is successful when the script exits cleanly and all three files exist.

## Stage 1 — Production inception

Perform on one device at a time, in this order. The script connects to real YubiKey devices via PIV.

1. **Laptop signer (signer 0):**
   - Insert laptop YubiKey
   - Run:
     ```bash
     python ceremony/incept.py \
         --production \
         --output-dir ~/locksmith-ceremony/01-laptop \
         --witness-oobi $(api-keri-host-oobi 1) \
         --witness-oobi $(api-keri-host-oobi 2) \
         --witness-oobi $(api-keri-host-oobi 3) \
         --yubikey-slot 9c
     ```
   - Enter PIV PIN when prompted
   - Confirm the AID prefix shown on screen
2. **Desktop signer (signer 1):** repeat on the desktop machine, contributing the second signature
3. **Air-gapped backup (signer 2):** boot the offline device, contribute the third signature, transfer signed event back via the USB drive

(The full *multi-device coordination* protocol — devices contributing partial signatures on separate machines that are merged later — is implemented in Phase 4 alongside the release-signing flow. In Phase 1 the inception event is built, signed, and submitted in a single run on one machine using all three devices physically attached. If only one YubiKey is available at ceremony time, run Stage 0 again and defer Stage 1 until both YubiKeys are present.)

## Stage 2 — Submit to witnesses

The ceremony script collects per-device signatures over the serialized inception event, attaches them as CESR signature blocks, and submits the signed stream to the api.keri.host witness pool. The pool returns one receipt per witness that accepted the event. The ceremony aborts if fewer than `toad` (default 2) receipts come back; the operator can retry the submission because witnesses are idempotent on event SAID.

After successful submission the publisher AID is **live**:

- Receipts are persisted alongside the inception event at `kel-events/icp-sn-0.receipts.json`
- `publisher-aid.json` is rewritten with `status: live` and the receipt count
- The publisher AID exists in the world and the KEL is now witnessed

Pass `--no-submit` to override this default (e.g. dry-run rehearsals on developer workstations).

## Stage 3 — Commit the trust anchor

After Stage 2 succeeds and witness receipts are gathered:

1. Copy `publisher_anchor.json` from the ceremony output directory to `src/locksmith/release/publisher_anchor.json` in a checkout of the repo
2. Inspect: confirm AID prefix is real (starts with `E`, not `PLACEHOLDER_`)
3. Commit:
   ```bash
   git add src/locksmith/release/publisher_anchor.json
   git commit -m "release: anchor production publisher AID"
   ```
4. Push and merge through normal review (this commit deserves a second pair of eyes — it is the trust root of every future release)

## Stage 4 — Publish to S3

After the trust anchor is committed:

```bash
aws s3 cp publisher-aid.json s3://releases.keri.host/publisher/v1/publisher-aid.json
aws s3 cp kel-events/ s3://releases.keri.host/publisher/v1/kel-events/ --recursive
```

CloudFront's `publisher/*` cache behavior is 60s TTL, so updates propagate quickly.

## Recovery procedures

| Scenario | Procedure |
|----------|-----------|
| One device lost or stolen | 2-of-3 quorum unaffected. Rotate keys (Phase 4 flow) to invalidate the missing device's key set. |
| Two devices lost | Quorum broken. Use air-gapped backup + emergency reissue. See `docs/governance/publisher-recovery.md` (deferred to Phase 4). |
| Suspected compromise | Immediate rotation. Pre-rotation digests in the most recent KEL event allow rotation within hours. |
| All three devices lost | Catastrophic. Publish abandonment notice via `keri.host` blog; users continue on the last verified version until a new AID + ceremony bootstraps trust. |

## Verification

After Stage 4 completes, any third party can independently verify the AID:

```bash
curl https://releases.keri.host/publisher/v1/publisher-aid.json
curl https://releases.keri.host/publisher/v1/kel-events/icp-sn-0.cesr -o icp.cesr
# Replay against api.keri.host witnesses to confirm inception event was witnessed
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/governance/publisher-ceremony.md
git commit -m "docs(governance): add publisher AID inception ceremony runbook"
```

---

### Task C2: Custodian device location placeholder

**Files:**
- Create: `docs/governance/publisher-custodians.md`

- [ ] **Step 1: Write the placeholder**

```markdown
# Publisher Custodian Devices

Physical inventory and location of the three signing devices that hold the publisher AID's 2-of-3 multisig key shares. **This document is sensitive — review access control before committing real location data.**

| Device label | Hardware | Serial | Physical location | Notes |
|--------------|----------|--------|-------------------|-------|
| Laptop signer | YubiKey 5 (model TBD) | TBD | TBD by operator | Daily-carry device. Replace YubiKey every 3 years or on suspected exposure. |
| Desktop signer | YubiKey 5 (model TBD) | TBD | TBD by operator | Office device. Keep physically secured when unattended. |
| Air-gapped backup | USB drive (model TBD) | TBD | Fireproof safe at TBD address | Powered on only during ceremonies. Never connected to a network. |

## Update procedure

1. Edit this file
2. Open a PR with the change
3. Two reviewers (the operator + one trusted reviewer) must approve
4. After merge, the operator confirms the physical state matches the recorded state

## Rotation triggers

- Annual scheduled rotation
- Device replacement (e.g. laptop refresh)
- Suspected compromise
- Operator change

When any of the above happens, follow the rotation procedure in `publisher-ceremony.md` Stage 1 with the new device(s), then update this file.
```

- [ ] **Step 2: Commit**

```bash
git add docs/governance/publisher-custodians.md
git commit -m "docs(governance): add publisher custodian device location template"
```

---

## Track D: Final integration + verification

### Task D1: End-to-end dry-run validation

This is the manual gate before the production ceremony. It confirms every component installed and works on the operator's actual machine.

- [ ] **Step 1: Run the full publisher test suite cleanly**

Run: `cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design/tools/publisher && source .venv/bin/activate && pytest -v`
Expected: All tests pass (no skips, no failures)

- [ ] **Step 2: Run the full infrastructure test suite cleanly**

Run: `cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design/infrastructure && pnpm exec jest`
Expected: All tests pass (~17 across files)

- [ ] **Step 3: Synth the CDK app to confirm it produces valid CloudFormation**

Run:
```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design/infrastructure
LOCKSMITH_AWS_ACCOUNT=111122223333 LOCKSMITH_AWS_REGION=us-east-1 CDK_DEFAULT_ACCOUNT=111122223333 CDK_DEFAULT_REGION=us-east-1 pnpm exec cdk synth --quiet
```
Expected: exit 0, `cdk.out/` populated with five stack templates

- [ ] **Step 4: Run the ceremony script in dry-run mode end-to-end**

Run:
```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design/tools/publisher
source .venv/bin/activate
python ceremony/incept.py \
    --dry-run \
    --output-dir /tmp/locksmith-phase1-validation \
    --witness-oobi https://staging.keri.host/witness/oobi/BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA \
    --witness-oobi https://staging.keri.host/witness/oobi/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB \
    --witness-oobi https://staging.keri.host/witness/oobi/BCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC \
    --non-interactive
```
Expected: exit 0; the three output files exist with non-empty content; the `publisher_anchor.json` has a real AID prefix (starts with `E`, not `PLACEHOLDER`)

- [ ] **Step 5: Confirm the placeholder publisher_anchor.json schema test still passes**

Run: `cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat+deploy-update-design && pytest tests/release/test_publisher_anchor_schema.py -v`
Expected: PASS

- [ ] **Step 6: Final commit (only if any tracking files changed)**

```bash
git status
# If there are no changes, skip the commit step entirely.
```

Phase 1 is complete when all five steps above pass cleanly and no uncommitted changes remain.

---

## Self-Review

Spec coverage check (each requirement in the user's brief mapped to a task):

1. **S3 bucket `releases.keri.host` with OAI** → Task A4
2. **CloudFront distribution + cache behaviors per spec §6.2** → Task A5 (3 cache behaviors with correct TTLs asserted)
3. **ACM cert in us-east-1** → Task A3
4. **Route 53 A/AAAA records** → Task A6
5. **GitHub Actions OIDC IAM role** → Task A7 (`gha-locksmith-release-publisher` with bucket-scoped permissions)
6. **CDK snapshot tests per stack** → A3, A4, A5, A6, A7 (each stack has a snapshot test + assertions)
7. **`tools/publisher/pyproject.toml`** → Task B1
8. **`__init__.py` + `cli.py`** → Task B1 and B2
9. **Subcommands stubbed; `incept` fully implemented** → Task B2 (stubs) + B7 (incept construction) + B9 (sign + submit)
10. **YubiKey integration documented (PIV slot)** → Task B3 (`9c` Digital Signature slot documented in module + ceremony) and `tools/publisher/README.md` (B1)
11. **`tools/publisher/ceremony/incept.py`** → Task B8 (initial dry-run runner) + B9 (`--submit` flag, signed + witnessed flow)
12. **2-of-3 multisig inception with `toad=2`** → Task B7 (`build_inception_event` asserts thresholds 2/2/2)
13. **Witnesses queried from api.keri.host** → Task B4 (`discover_witness_pool`, pool listing) + Task B5 (`WitnessClient` per-witness HTTP)
14. **Pre-rotation commitment** → Task B7 (`next_digests` generation + assertion in test)
15. **§7.5 step 4 — Submission to witnesses, collect receipts** → Task B5 (`WitnessClient.submit_event`) + Task B9 (signed inception event submitted; ≥`toad` receipts asserted; receipts persisted to `kel-events/icp-sn-0.receipts.json`; `publisher-aid.json` marked `status=live`). Phase 1 makes the publisher AID live; Phase 4 reuses the same `WitnessClient` for release `ixn` events.
16. **Output `src/locksmith/release/publisher_anchor.json`** → Task B6 (emitter) + B10 (placeholder committed; real version overwrites after ceremony)
17. **Output S3 publisher-aid.json + kel-events/** → Task B6 (`write_publisher_summary`) + B7 (kel-events file emission) + B9 (receipts file + live-state summary) + `publisher-ceremony.md` Stage 4 (S3 upload commands)
18. **`docs/governance/publisher-ceremony.md`** → Task C1 (Stage 2 updated for in-phase submission)
19. **`docs/governance/publisher-custodians.md` placeholder with TBD** → Task C2
20. **`infrastructure/README.md`** → Task A9
21. **CDK snapshot tests (TypeScript)** → All A-track stack tasks
22. **Python unit tests for `incept`** → Task B7 (construction) + Task B9 (signing + submission with mocked `WitnessClient`); uses fake witness pool, not api.keri.host
23. **Manual ceremony dry-run against staging witnesses** → Task D1 Step 4
24. **No app code changes** → confirmed; only new files under `infrastructure/`, `tools/publisher/`, `src/locksmith/release/`, `docs/governance/`, `tests/release/`
25. **No build pipeline changes** → confirmed; `.github/workflows/release.ci.yml` is untouched
26. **`publisher_anchor.json` consumed by Phase 2/3** → committed placeholder is real-file-shaped so embedding works
27. **S3 bucket + OIDC role consumed by Phases 2/3/4** → bucket name and role name are constants in `infrastructure/lib/config.ts`, exported via stack outputs

### Cross-phase dependencies — confirmed

**Phase 1 owns and delivers** (consumed by later phases):
- `infrastructure/` CDK stacks → S3 bucket + CloudFront + OIDC role consumed by Phases 2/3/4
- `src/locksmith/release/publisher_anchor.json` (placeholder shape now, real values after ceremony) → embedded by Phases 2/3 builds; read by Phase 4 verifier
- `tools/publisher/src/locksmith_publisher/witness_client.py` — **owned by Phase 1**; the `WitnessClient` / `Receipt` / `KeyState` / `WitnessThresholdNotMet` / `WitnessDuplicityDetected` / `WitnessUnreachable` symbols are imported unchanged by Phase 4's release `ixn` flow (Phase 4 Task 12 confirms no extension required and is scoped to integration-only)
- Publisher AID **live** on api.keri.host with `toad=2` witness receipts at inception SN=0 — Phase 4's KEL replay starts from this state
- `tools/publisher/` package skeleton with `incept` fully implemented and `sign` / `countersign` / `submit` / `verify-ceremony` left as Phase-4 stubs

**Phase 1 has no upstream phase dependencies.**

Placeholder scan: no "TBD" in implementation code; the only TBDs are in `publisher-custodians.md` which is explicitly a template for the user to fill in physical device info, and the placeholder `publisher_anchor.json` which is functionally required (the file must exist for the app to build before the production ceremony happens).

Type consistency: `PublisherAnchor`, `WitnessInfo`, `YubiKeyDevice` / `FakeYubiKeyDevice`, `InceptionResult`, and `WitnessClient` / `Receipt` / `KeyState` field names match across `anchor.py`, `witnesses.py`, `witness_client.py`, `yubikey.py`, `incept.py`, and the ceremony script. `ReleasesConfig` constants (`DOMAIN_NAME`, `IAM_ROLE_NAME`, `GITHUB_REPO`, etc.) match across all five CDK stacks and the README.

Self-review complete.
