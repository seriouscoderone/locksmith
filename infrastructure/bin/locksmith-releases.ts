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
  existingOidcProviderArn: process.env.LOCKSMITH_EXISTING_OIDC_PROVIDER_ARN,
  env: primaryEnv,
});
iamOidc.addDependency(bucket);

app.synth();
