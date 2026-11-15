#!/usr/bin/env bash
# Remove everything scripts/aws_demo_setup.sh created.
set -uo pipefail
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
NAME=oncallai-alarms

aws cloudwatch delete-alarms --alarm-names checkout-service-error-burst
aws logs delete-metric-filter --log-group-name /oncallai-demo/checkout-service --filter-name checkout-errors
TOPIC_ARN=$(aws sns list-topics --query "Topics[?ends_with(TopicArn, ':$NAME')].TopicArn | [0]" --output text)
if [ -n "$TOPIC_ARN" ] && [ "$TOPIC_ARN" != "None" ]; then
  for sub in $(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --query 'Subscriptions[].SubscriptionArn' --output text); do
    [ "$sub" != "PendingConfirmation" ] && aws sns unsubscribe --subscription-arn "$sub"
  done
  aws sns delete-topic --topic-arn "$TOPIC_ARN"
fi
QUEUE_URL=$(aws sqs get-queue-url --queue-name "$NAME" --query QueueUrl --output text 2>/dev/null) && \
  aws sqs delete-queue --queue-url "$QUEUE_URL"
for g in /oncallai-demo/checkout-service /oncallai-demo/payment-service; do
  aws logs delete-log-group --log-group-name "$g"
done
echo "Removed the OnCallAI demo resources."
