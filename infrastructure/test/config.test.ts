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
