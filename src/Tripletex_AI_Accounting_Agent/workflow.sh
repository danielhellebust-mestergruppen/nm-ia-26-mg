#!/bin/bash
# Competition workflow: pull → analyze → fix → deploy → submit
# Usage:
#   ./workflow.sh pull      — Pull logs, analyze latest submissions
#   ./workflow.sh deploy    — Quick deploy to Cloud Run
#   ./workflow.sh cycle     — Pull logs + update few-shot examples + deploy
#   ./workflow.sh status    — Show current score summary

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

case "${1:-help}" in

pull)
    echo -e "${YELLOW}Pulling logs...${NC}"
    gcloud logging read \
      'resource.type="cloud_run_revision" AND resource.labels.service_name="tripletex-agent"' \
      --limit 5000 \
      --freshness=48h \
      --format="value(timestamp, textPayload)" \
      | grep -v "^$" > logs/gcp-raw-all.log

    echo "$(wc -l < logs/gcp-raw-all.log) log lines"

    python3 logs/parse_logs.py logs/gcp-raw-all.log

    echo ""
    echo -e "${YELLOW}Latest 5 submissions (CET):${NC}"
    python3 -c "
import json
from datetime import datetime, timedelta
with open('logs/submissions.json') as f:
    subs = json.load(f)
for s in subs[-5:]:
    t = s['timestamp'][:19]
    try:
        utc = datetime.fromisoformat(t.replace('Z',''))
        t = (utc + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    except: t = t.replace('T',' ')
    status = '✓' if s['status'] == 'ok' else '✗'
    apis = s.get('api_calls_count') or len(s.get('api_calls', []))
    err = s.get('error', '')[:60] if s.get('error') else ''
    print(f'  {status} {t} {s[\"task_type\"]:<25} apis={apis} {err}')
"

    echo ""
    echo -e "${YELLOW}Failure analysis:${NC}"
    python3 -c "
import json
from collections import Counter
with open('logs/submissions.json') as f:
    subs = json.load(f)
errors = [s for s in subs if s['status'] != 'ok']
ok = [s for s in subs if s['status'] == 'ok']
print(f'  Total: {len(subs)} submissions, {len(ok)} ok, {len(errors)} failed')
if errors:
    print(f'  Failed task types:')
    for task, count in Counter(s['task_type'] for s in errors).most_common():
        print(f'    {task}: {count}')
    print(f'  Recent errors:')
    for s in errors[-3:]:
        err = s.get('error', 'unknown')[:100]
        print(f'    [{s[\"task_type\"]}] {err}')
"
    ;;

deploy)
    echo -e "${YELLOW}Deploying to Cloud Run...${NC}"
    gcloud run deploy tripletex-agent \
      --source . \
      --region europe-north1 \
      --memory 2Gi \
      --cpu 2 \
      --timeout 300 \
      --allow-unauthenticated \
      --min-instances 1 \
      --set-env-vars "GOOGLE_API_KEY=${GOOGLE_API_KEY}"
    echo -e "${GREEN}Deployed! Ready for submissions.${NC}"
    ;;

cycle)
    echo -e "${YELLOW}=== FULL CYCLE ===${NC}"

    # 1. Pull and analyze
    echo -e "${YELLOW}Step 1: Pull logs${NC}"
    $0 pull

    # 2. Auto-learn: update few-shot examples + analyze patterns
    echo ""
    echo -e "${YELLOW}Step 2: Auto-learn from submissions${NC}"
    python3 -c "
import json
from llm.examples import load_examples

# Load current examples
examples = load_examples()
print(f'  {len(examples)} few-shot examples loaded')

# Analyze success patterns from submissions
with open('logs/submissions.json') as f:
    subs = json.load(f)

ok = [s for s in subs if s['status'] == 'ok']
fail = [s for s in subs if s['status'] != 'ok']
types_seen = set(s.get('task_type','') for s in subs)
types_ok = set(s.get('task_type','') for s in ok)
types_fail = set(s.get('task_type','') for s in fail) - types_ok

print(f'  {len(ok)}/{len(subs)} successful submissions')
print(f'  Task types with 0% success: {types_fail or \"none\"}')

# Show per-type success rates
from collections import Counter
type_ok = Counter(s.get('task_type','') for s in ok)
type_all = Counter(s.get('task_type','') for s in subs)
print(f'  Per-type rates:')
for t, total in type_all.most_common():
    rate = 100 * type_ok.get(t, 0) // total
    if rate < 100:
        print(f'    {t}: {type_ok.get(t,0)}/{total} ({rate}%)')
"

    # 3. Deploy
    echo ""
    echo -e "${YELLOW}Step 3: Deploy${NC}"
    $0 deploy
    ;;

status)
    echo -e "${YELLOW}Score summary:${NC}"
    python3 -c "
import json
from collections import defaultdict
with open('logs/submissions.json') as f:
    subs = json.load(f)

by_type = defaultdict(lambda: {'attempts': 0, 'successes': 0})
for s in subs:
    by_type[s['task_type']]['attempts'] += 1
    if s['status'] == 'ok':
        by_type[s['task_type']]['successes'] += 1

total_ok = sum(v['successes'] for v in by_type.values())
total = sum(v['attempts'] for v in by_type.values())
print(f'  Overall: {total_ok}/{total} successful ({100*total_ok//max(total,1)}%)')
print(f'  Task types seen: {len(by_type)}')
print()
for task, stats in sorted(by_type.items()):
    rate = 100*stats['successes']//max(stats['attempts'],1)
    bar = '✓' * stats['successes'] + '✗' * (stats['attempts'] - stats['successes'])
    print(f'  {task:<25} {bar} ({rate}%)')
"
    ;;

tail)
    echo -e "${YELLOW}Tailing live logs (Ctrl+C to stop)...${NC}"
    gcloud beta run services logs tail tripletex-agent --region europe-north1 2>/dev/null || \
    gcloud logging tail 'resource.type="cloud_run_revision" AND resource.labels.service_name="tripletex-agent"' --format="value(textPayload)"
    ;;

test)
    echo -e "${YELLOW}Running sandbox tests...${NC}"
    python3 tests/accounting_test_suite.py
    ;;

help)
    echo "Competition workflow commands:"
    echo "  ./workflow.sh pull     — Pull GCP logs + analyze"
    echo "  ./workflow.sh deploy   — Deploy to Cloud Run"
    echo "  ./workflow.sh cycle    — Pull + update examples + deploy"
    echo "  ./workflow.sh status   — Score summary by task type"
    echo "  ./workflow.sh tail     — Live log tail"
    echo "  ./workflow.sh test     — Run sandbox test suite"
    ;;

esac
