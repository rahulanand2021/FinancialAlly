$diff = git diff HEAD
$untracked = git ls-files --others --exclude-standard

if ([string]::IsNullOrWhiteSpace($diff) -and [string]::IsNullOrWhiteSpace($untracked)) {
    exit 0
}

$changes = $diff
if (-not [string]::IsNullOrWhiteSpace($untracked)) {
    $changes += "`n`nNew untracked files:`n$untracked"
}

$prompt = @"
You are reviewing code changes. Do the following:
1. Summarize the changes
2. Identify bugs or risks
3. Suggest improvements
4. Output results in markdown format

Append results to planning/REVIEW.md

Here are the changes:

$changes
"@

$prompt | claude -p
