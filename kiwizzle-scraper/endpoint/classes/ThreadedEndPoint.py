import logging
import threading

import config
from endpoint.classes.EndPoint import EndPoint

logger = logging.getLogger(config.LOGGER_NAME)


class ThreadedEndPoint(EndPoint):
    def init_context(self, company_name):
        super().init_context(company_name)
        self.result_counts = {}

    def extract_descs_to_queue_worker(self, thread_index):
        thread_success_count, thread_new_success_count = 0, 0
        self.result_counts[thread_index] = [thread_success_count, thread_new_success_count]
        for desc_wrapper in self.extract_from_endpoint():
            desc_data = self.pack_desc_for_rest(desc_wrapper)
            if desc_data is None or not desc_data["isNew"]:
                continue
            logger.debug(
                f"[{self.__class__.__name__}] {self.extract_descs_to_queue_worker.__name__}() desc_data:" + str(
                    desc_data))
            if self.send_desc_to_api_server_entry(desc_data):
                thread_success_count += 1
                if desc_data["isNew"]:
                    thread_new_success_count += 1
        self.result_counts[thread_index] = [thread_success_count, thread_new_success_count]

    def extract_desc_and_send_to_api_server(self):
        existing_count, success_count, new_success_count = 0, 0, 0
        self.extract_job_list()
        existing_count = len(self.page_queue.queue)

        hashs = list(map(lambda x: x["hash"], list(self.page_queue.queue)))
        self.report_existing_hashs_to_api_server(hashs, self.company_id)
        thread_list = []
        for thread_index in range(0, config.NUM_WORKERS):
            scraping_thread = threading.Thread(target=self.extract_descs_to_queue_worker, args=(thread_index,))
            scraping_thread.start()
            thread_list.append(scraping_thread)

        for thread in thread_list:
            thread.join()

        for thread_index in range(0, config.NUM_WORKERS):
            thread_success_count, thread_new_success_count = self.result_counts[thread_index]
            success_count += thread_success_count
            new_success_count += thread_new_success_count
        return existing_count, success_count, new_success_count
