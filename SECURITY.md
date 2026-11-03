# Security and data handling

Treat original NOP data, derived observations, model provenance and business reports according to the project owner's access policy. Keep this business-data repository private unless its owner authorizes distribution. Repository configuration is not authorization to publish its contents.

Load `.joblib` artifacts only from trusted project deliveries. Their loading mechanism can execute Python code. Verify artifact hashes and metadata, use the recorded dependency versions, and preserve the exploratory/approval status in integration outputs.

For a security issue, use GitHub private vulnerability reporting if the repository owner has enabled it. Otherwise contact the maintainer privately through the team's established channel. Share a minimal redacted reproduction and affected versions; keep source records and credentials out of public issues.
