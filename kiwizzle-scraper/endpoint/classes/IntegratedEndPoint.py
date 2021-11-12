import logging

import config
from endpoint.classes.EndPoint import EndPoint

logger = logging.getLogger(config.LOGGER_NAME)


class IntegratedEndPoint(EndPoint):
    def init_integrated_context(self, default_name, company_names):
        super().init_context(default_name)
        self.company_ids = {}
        self.result_counts = {}
        for NAME in company_names.values():
            company_id = self.get_company_id_from_api_server(NAME)
            self.company_ids[NAME] = company_id
            self.result_counts[company_id] = [0, 0, 0]

    def extract_desc_and_send_to_api_server(self):
        self.extract_job_list()
        for name in self.company_ids:
            company_id = self.company_ids[name]
            hashs = list(
                map(lambda x: x["hash"], filter(lambda x: x["company_id"] == company_id, list(self.page_queue.queue))))
            self.result_counts[company_id][0] = len(hashs)
            self.report_existing_hashs_to_api_server(hashs, company_id)

        for desc_wrapper in self.extract_from_endpoint():
            desc_data = self.pack_desc_for_rest(desc_wrapper)
            if desc_data is None or not desc_data["isNew"]:
                continue
            logger.debug(f"[{self.__class__.__name__}] extract_descs_to_queue() desc_data:" + str(desc_data))
            if self.send_desc_to_api_server_entry(desc_data):
                company_id = desc_data["companyId"]
                self.result_counts[company_id][1] += 1
                if desc_data["isNew"]:
                    self.result_counts[company_id][2] += 1
        total_existing_count, total_success_count, total_success_new_count = 0, 0, 0

        for name in self.company_ids:
            company_id = self.company_ids[name]
            existing_count, success_count, success_new_count = self.result_counts[company_id]
            total_existing_count += existing_count
            total_success_count += success_count
            total_success_new_count += success_new_count
            logger.info(
                f"{self.__class__.__name__}:{name} results existing_count:{existing_count}, success_count: {success_count}, success_new_count: {success_new_count}")
        return total_existing_count, total_success_count, total_success_new_count
