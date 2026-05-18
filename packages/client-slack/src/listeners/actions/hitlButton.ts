import { App } from '@slack/bolt';
import { Logger } from '../../utils/logger.js';
import { handleIncomingMessage, HandlerDependencies, NormalizedMessage } from '../events/messageHandler.js';

/**
 * Register handlers for generic HITL interrupt widget interactions.
 * Users can approve/reject any tool that triggers a human-in-the-loop interrupt,
 * and optionally provide additional details via a modal.
 *
 * Button values encode taskId, contextId, toolName, reason as base64 JSON
 * to pass context through Slack's action flow.
 */
export function registerHitlActions(app: App, makeDeps: () => HandlerDependencies): void {
  const logger = Logger.getLogger('hitlButton');

  /**
   * Handle "Reject" button - send reject decision to orchestrator
   */
  app.action('hitl_reject', async ({ ack, body, client }) => {
    await ack();
    
    const userId = body.user?.id;
    const action = (body as any).actions?.[0];
    const actionValue = action?.value || '';
    const channelId = (body as any).channel?.id;
    const messageTs = (body as any).message?.ts;
    const threadTs = (body as any).message?.thread_ts || messageTs;

    if (!actionValue || !userId || !channelId || !messageTs) {
      logger.warn(`Missing required values in hitl_reject action`);
      return;
    }

    try {
      const decodedValue = JSON.parse(Buffer.from(actionValue, 'base64').toString());
      const { taskId, toolName } = decodedValue;

      logger.info(`HITL rejected by user ${userId} for task ${taskId} tool ${toolName}`);

      // Remove the interactive widget (orchestrator will post the outcome)
      await client.chat.delete({
        channel: channelId,
        ts: messageTs,
      });

      // Send reject decision to orchestrator via handleIncomingMessage
      const decisions = { decisions: [{ type: 'reject', message: 'The user explicitly rejected this tool call via the human-in-the-loop approval. The tool was NOT executed. Do not retry or attempt workarounds unless the user explicitly asks.' }] };
      const syntheticMessage: NormalizedMessage = {
        userId,
        teamId: (body as any).team?.id || '',
        channelId,
        messageTs: messageTs || Date.now().toString(),
        threadTs,
        rawText: '',
        dataParts: [decisions],
        source: 'direct_message',
        client,
      };

      handleIncomingMessage(syntheticMessage, makeDeps()).catch((err) => {
        logger.error(err, `Failed to send HITL reject to orchestrator: ${err}`);
      });
    } catch (error) {
      logger.error(error, `Failed to process hitl_reject: ${error}`);
    }
  });

  /**
   * Handle "Approve" button - open modal for optional edits
   */
  app.action('hitl_approve', async ({ ack, body, client }) => {
    await ack();
    const logger = Logger.getLogger('hitlButton');

    const userId = body.user?.id;
    const action = (body as any).actions?.[0];
    const actionValue = action?.value || '';
    const triggerId = (body as any).trigger_id;
    const messageTs = (body as any).message?.ts;

    if (!actionValue || !userId || !triggerId) {
      logger.warn(`Missing required values in hitl_approve action`);
      return;
    }

    try {
      const decodedValue = JSON.parse(Buffer.from(actionValue, 'base64').toString());
      const { taskId, contextId, toolName, reason, channelId, threadTs, actionRequests } = decodedValue;

      logger.info(`HITL approve clicked by user ${userId} for task ${taskId} tool ${toolName}`);

      // Encode callback data in private_metadata
      const privateMetadata = JSON.stringify({
        taskId,
        contextId,
        toolName,
        reason,
        channelId,
        threadTs,
        messageTs,
        actionRequests,
      });

      const toolLabel = (toolName || 'unknown').replace(/_/g, ' ');

      // Open modal for optional edits
      await client.views.open({
        trigger_id: triggerId,
        view: {
          type: 'modal',
          callback_id: 'hitl_submit',
          private_metadata: privateMetadata,
          title: {
            type: 'plain_text',
            text: 'Approve Action',
            emoji: true,
          },
          submit: {
            type: 'plain_text',
            text: 'Approve',
            emoji: true,
          },
          close: {
            type: 'plain_text',
            text: 'Cancel',
            emoji: true,
          },
          blocks: [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `*Tool:* ${toolLabel}\n*Reason:* ${reason}`,
              },
            },
            {
              type: 'divider',
            },
            {
              type: 'input',
              block_id: 'description_block',
              optional: true,
              label: {
                type: 'plain_text',
                text: 'Additional details or edits (optional)',
                emoji: true,
              },
              element: {
                type: 'plain_text_input',
                action_id: 'description_input',
                multiline: true,
                placeholder: {
                  type: 'plain_text',
                  text: 'Add extra context or modify the action...',
                },
              },
            },
          ],
        },
      });
    } catch (error) {
      logger.error(error, `Failed to open HITL approval modal: ${error}`);
    }
  });

  logger.info('Registered HITL action handlers');
}
