import json

from azure.core.exceptions import AzureError
from azure.servicebus import ServiceBusReceiver, ServiceBusSender, ServiceBusMessage

import service_bus_base
from message_parser import ServiceBusMessageParser


class TopicProcess(service_bus_base.ServiceBusBase):

    def __init__(self, ctx):
        service_bus_base.ServiceBusBase.__init__(self, ctx)

    def spying_message(self):
        with self.service_bus_client:

            if self.ctx.obj['GET_QUEUE_PROPERTIES']:
                TopicProcess.get_sub_properties(self)

            receiver = TopicProcess.get_receiver(self)

            with receiver:
                sequence_number = 0
                for x in range(self.ctx.obj['PAGES']):
                    if sequence_number == 0:
                        received_msgs = receiver.peek_messages(max_message_count=self.ctx.obj['MAX_MESSAGE_COUNT'])
                    else:
                        received_msgs = receiver.peek_messages(max_message_count=self.ctx.obj['MAX_MESSAGE_COUNT'],
                                                               sequence_number=sequence_number+1)

                    self.custom_log_obj.log_info("%s %s" % ('Number of messages: ', len(received_msgs),))

                    for msg in received_msgs:
                        if self.ctx.obj['PRETTY']:
                            TopicProcess.log_message_pretty(self, msg)
                        else:
                            TopicProcess.log_message(self, msg)
                        sequence_number = msg.sequence_number

    def get_sub_properties(self):
        self.custom_log_obj.log_info("-- Get Subscription Runtime Properties")
        try:
            get_sub_runtime_properties = self.servicebus_mgmt_client.get_subscription_runtime_properties(
                topic_name=self.ctx.obj['TOPIC_NAME'], subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'])

            get_sub_properties = self.servicebus_mgmt_client.get_subscription(
                topic_name=self.ctx.obj['TOPIC_NAME'], subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'])

            self.custom_log_obj.log_info("-- Subscription Information")
            self.custom_log_obj.log_info("%s %s" % ('Status:', get_sub_properties.status,))
            self.custom_log_obj.log_info("%s %s" % ('Queue name:', get_sub_runtime_properties.name,))
            self.custom_log_obj.log_info("%s %s" % ('Forward to: ', get_sub_properties.forward_to,))
            self.custom_log_obj.log_info("%s %s" % ('Forward to dead lettered: ', get_sub_properties.forward_dead_lettered_messages_to,))
            self.custom_log_obj.log_info("%s %s" % ('Created at utc: ', get_sub_runtime_properties.created_at_utc,))
            self.custom_log_obj.log_info("%s %s" % ('Updated at utc: ', get_sub_runtime_properties.updated_at_utc,))
            self.custom_log_obj.log_info("%s %s" % ('Accessed at utc: ', get_sub_runtime_properties.accessed_at_utc,))
            self.custom_log_obj.log_info(
                "%s %s" % ('Active message count:', get_sub_runtime_properties.active_message_count,))
            self.custom_log_obj.log_info(
                "%s %s" % ('Dead letter message count:', get_sub_runtime_properties.dead_letter_message_count,))
            self.custom_log_obj.log_info(
                "%s %s" % ('Transfer message count:', get_sub_runtime_properties.transfer_message_count,))
            self.custom_log_obj.log_info("%s %s" % (
            'Transfer DLQ message count:', get_sub_runtime_properties.transfer_dead_letter_message_count,))
            self.custom_log_obj.log_info(
                "%s %s" % ('Message count:', get_sub_runtime_properties.total_message_count,))

        except AzureError:
            self.custom_log_obj.log_info("Not authorized or invalid request to obtaining subscription runtime properties")

    def purge(self):
        self.custom_log_obj.log_info("Purge subscription started. Wait for completion")

        TopicProcess.__purge_recursive(self, self.ctx.obj['MAX_MESSAGE_COUNT'])

        self.custom_log_obj.log_info("Purge subscription completed")

    def __purge_recursive(self, max_message_count):
        if self.ctx.obj['TO_DEAD_LETTER']:
            receiver = TopicProcess.get_receiver(self)
        else:
            receiver = TopicProcess.get_receiver_mode(self, self.ServiceBusReceiveMode.RECEIVE_AND_DELETE)

        with receiver:
            received_msgs = receiver.receive_messages(max_message_count=max_message_count, max_wait_time=5)
            len_received_msgs = len(received_msgs)
            for msg in received_msgs:
                if self.ctx.obj['LOG_PATH'] is not None:
                    receiver.complete_message(msg)
                    TopicProcess.log_message(self, msg)
                if self.ctx.obj['TO_DEAD_LETTER'] and not self.ctx.obj['DEAD_LETTER']:
                    receiver.dead_letter_message(msg)

        self.custom_log_obj.log_info("%s %s" % ('Length received_msgs: ', len_received_msgs,))

        if len_received_msgs is not None and len_received_msgs > 0:
            TopicProcess.__purge_recursive(self, max_message_count)

    def get_receiver(self) -> ServiceBusReceiver:
        if self.ctx.obj['DEAD_LETTER']:
            if self.ctx.obj['USE_SESSION']:
                receiver = self.service_bus_client\
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               sub_queue=self.DEAD_LETTER, session_id=self.ctx.obj['SESSION'])
            else:
                receiver = self.service_bus_client \
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               sub_queue=self.DEAD_LETTER)
        else:
            if self.ctx.obj['USE_SESSION']:
                receiver = self.service_bus_client\
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'], session_id=self.ctx.obj['SESSION'])
            else:
                receiver = self.service_bus_client \
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'])

        return receiver

    def get_sender(self) -> ServiceBusSender:
        return self.service_bus_client.get_topic_sender(topic_name=self.ctx.obj['TOPIC_NAME'])

    def get_receiver_mode(self, receive_mode: str) -> ServiceBusReceiver:
        if self.ctx.obj['DEAD_LETTER']:
            if self.ctx.obj['USE_SESSION']:
                receiver = self.service_bus_client\
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               sub_queue=self.DEAD_LETTER, receive_mode=receive_mode, session_id=self.ctx.obj['SESSION'])
            else:
                receiver = self.service_bus_client \
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               sub_queue=self.DEAD_LETTER, receive_mode=receive_mode)
        else:
            if self.ctx.obj['USE_SESSION']:
                receiver = self.service_bus_client\
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               receive_mode=receive_mode, session_id=self.ctx.obj['SESSION'])
            else:
                receiver = self.service_bus_client \
                    .get_subscription_receiver(topic_name=self.ctx.obj['TOPIC_NAME'],
                                               subscription_name=self.ctx.obj['SUBSCRIPTION_NAME'],
                                               receive_mode=receive_mode)

        return receiver

    def message(self, input_file):
        json_messages = json.load(input_file)

        with self.service_bus_client:
            sender = self.get_sender()
            with sender:
                batch_message = sender.create_message_batch()
                count = 0
                for message in json_messages:
                    message_parser = ServiceBusMessageParser(**message)
                    message_obj = message_parser.get_service_bus_message()
                    if self.ctx.obj['USE_SESSION']:
                        if message_obj.session_id is None or message_obj.session_id == '':
                            message_obj.session_id = self.ctx.obj['SESSION']
                    try:
                        batch_message.add_message(message_obj)
                        count += 1
                    except ValueError:
                        # ServiceBusMessageBatch object reaches max_size.
                        # New ServiceBusMessageBatch object can be created here to send more data.
                        pass

                sender.send_messages(batch_message)
                self.custom_log_obj.log_info("%s %s %s %s" % ('Messages sent. Size in bytes: ',
                                                              batch_message.size_in_bytes, ', Count: ', count))

