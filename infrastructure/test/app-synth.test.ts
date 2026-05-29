import { execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

jest.setTimeout(120000);

describe('cdk app', () => {
  test('synthesizes all five stacks without error', () => {
    const infraDir = path.resolve(__dirname, '..');
    execSync('npx cdk synth --quiet', {
      cwd: infraDir,
      env: {
        ...process.env,
        LOCKSMITH_AWS_ACCOUNT: '111122223333',
        LOCKSMITH_AWS_REGION: 'us-east-1',
        CDK_DEFAULT_ACCOUNT: '111122223333',
        CDK_DEFAULT_REGION: 'us-east-1',
      },
      stdio: ['ignore', 'ignore', 'ignore'],
    });

    const cdkOutDir = path.join(infraDir, 'cdk.out');
    expect(fs.existsSync(path.join(cdkOutDir, 'LocksmithReleasesCert.template.json'))).toBe(true);
    expect(fs.existsSync(path.join(cdkOutDir, 'LocksmithReleasesBucket.template.json'))).toBe(true);
    expect(fs.existsSync(path.join(cdkOutDir, 'LocksmithReleasesCdn.template.json'))).toBe(true);
    expect(fs.existsSync(path.join(cdkOutDir, 'LocksmithReleasesDns.template.json'))).toBe(true);
    expect(fs.existsSync(path.join(cdkOutDir, 'LocksmithReleasesIamOidc.template.json'))).toBe(true);
  });
});
