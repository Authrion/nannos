import { App } from '@slack/bolt';
import { Logger } from '../../utils/logger.js';
import { handleIncomingMessage, HandlerDependencies, NormalizedMessage } from '../events/messageHandler.js';

/**
 * Register handler for generic HITL approval modal submission.
 * When user submits the modal, we send the HITL decision directly to the
 * orchestrator via handleIncomingMessage (not by posting a Slack message).
 */
export function registerHitlModalHandler(app: App, makeDeps: () => HandlerDependencies): void {
  const logger = Logger.getLogger('hitlModal');

  app.view('hitl_submit', async ({ ack, body, view, client }) => {
    await ack();

    const userId = body.user.id;
    logger.info(`HITL modal submitted by user ${userId}`);

    let privateMetadata: any;
    try {
      privateMetadata = JSON.parse(view.private_metadata);
      const { channelId, threadTs, messageTs, toolName, actionRequests } = privateMetadata;

      // Extract description from form
      const descriptionBlock = view.state?.values?.description_block;
      const description = descriptionBlock?.description_input?.value;

      // Build HITL decisions payload in the format expected by HumanInTheLoopMiddleware
      let decisions: Record<string, unknown>;
      if (description) {
        // "edit" decision: merge user's description into original tool args
        const originalAction = actionRequests?.[0] || {};
        const editedArgs = { ...(originalAction.args || {}), description };
        decisions = {
          decisions: [{ type: 'edit', edited_action: { name: originalAction.name || toolName, args: editedArgs } }],
        };
      } else {
        decisions = { decisions: [{ type: 'approve' }] };
      }

      // Send as a synthetic user message via handleIncomingMessage
      // This routes it to the orchestrator with the correct context ID
      const syntheticMessage: NormalizedMessage = {
        userId,
        teamId: body.team?.id || '',
        channelId,
        messageTs: messageTs || Date.now().toString(),
        threadTs,
        rawText: '',
        dataParts: [decisions],
        source: 'direct_message',
        client,
      };

      // Remove the interactive widget (orchestrator will post the outcome)
      await client.chat.delete({
        channel: channelId,
        ts: messageTs,
      });

      // Fire the message to the orchestrator (async, don't await the full stream)
      handleIncomingMessage(syntheticMessage, makeDeps()).catch((err) => {
        logger.error(err, `Failed to send HITL approval to orchestrator: ${err}`);
      });

      logger.info(`HITL approval sent to orchestrator for tool ${toolName}`);
    } catch (error) {
      logger.error(error, `Failed to process HITL modal submission: ${error}`);
      if (privateMetadata?.channelId && privateMetadata?.threadTs) {
        await client.chat.postMessage({
          channel: privateMetadata.channelId,
          thread_ts: privateMetadata.threadTs,
          text: `❌ Failed to process approval: ${error instanceof Error ? error.message : 'unknown error'}`,
        });
      }
    }
  });

  logger.info('Registered HITL modal handler');
}
