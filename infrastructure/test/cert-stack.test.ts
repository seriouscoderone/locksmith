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
