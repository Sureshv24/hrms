-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: localhost    Database: hrms_db
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `attendance`
--

DROP TABLE IF EXISTS `attendance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `attendance_date` date NOT NULL,
  `check_in` datetime NOT NULL,
  `check_out` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_employee_attendance_date` (`employee_id`,`attendance_date`),
  KEY `ix_attendance_attendance_date` (`attendance_date`),
  KEY `ix_attendance_employee_id` (`employee_id`),
  KEY `ix_attendance_id` (`id`),
  CONSTRAINT `attendance_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `ck_attendance_checkout_after_checkin` CHECK (((`check_out` is null) or (`check_out` >= `check_in`)))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attendance`
--

LOCK TABLES `attendance` WRITE;
/*!40000 ALTER TABLE `attendance` DISABLE KEYS */;
INSERT INTO `attendance` VALUES (1,1,'2026-10-13','2026-10-13 03:30:00','2026-10-13 12:30:00','2026-10-13 08:40:02'),(2,1,'2026-10-14','2026-10-14 08:39:55',NULL,'2026-10-14 14:09:55');
/*!40000 ALTER TABLE `attendance` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `actor_user_id` int DEFAULT NULL,
  `actor_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_role` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_audit_logs_created_at` (`created_at`),
  KEY `ix_audit_logs_action` (`action`),
  KEY `ix_audit_logs_actor_user_id` (`actor_user_id`),
  KEY `ix_audit_logs_entity_type` (`entity_type`),
  KEY `ix_audit_logs_id` (`id`),
  KEY `ix_audit_logs_entity_id` (`entity_id`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
INSERT INTO `audit_logs` VALUES (1,2,'magesh','Admin','employee.updated','employee','1','{\"employee_code\": \"EMP001\", \"changed_fields\": [\"address\", \"department\", \"designation\", \"joining_date\", \"phone\", \"salary\"]}','2026-10-13 15:10:50'),(2,1,'suresh','Employee','leave.applied','leave','2','{\"status\": \"Pending\", \"end_date\": \"2026-10-22\", \"leave_type\": \"Casual\", \"start_date\": \"2026-10-22\", \"employee_id\": 1}','2026-10-13 15:15:50'),(3,2,'magesh','Admin','leave.approved','leave','2','{\"status\": \"Approved\", \"end_date\": \"2026-10-22\", \"lop_days\": 0, \"leave_type\": \"Casual\", \"start_date\": \"2026-10-22\", \"employee_id\": 1}','2026-10-13 15:16:40'),(4,2,'magesh','Admin','payroll.generated','payroll','2','{\"year\": 2026, \"month\": 11, \"status\": \"Generated\", \"lop_days\": 0, \"net_salary\": \"25000.00\", \"employee_id\": 1, \"gross_salary\": \"25000.00\", \"present_days\": 0, \"lop_deduction\": \"0.00\"}','2026-10-13 15:30:03'),(5,2,'magesh','Admin','payroll.locked','payroll','2','{\"year\": 2026, \"month\": 11, \"status\": \"Locked\", \"net_salary\": \"25000.00\", \"employee_id\": 1}','2026-10-13 15:31:50'),(6,2,'magesh','Admin','payroll.credit_simulated','payroll','2','{\"year\": 2026, \"month\": 11, \"status\": \"Paid\", \"net_salary\": \"25000.00\", \"employee_id\": 1, \"payment_type\": \"simulation_only\"}','2026-10-13 15:34:24'),(7,2,'magesh','Admin','payroll.generated','payroll','3','{\"year\": 2026, \"month\": 10, \"status\": \"Generated\", \"lop_days\": 0, \"net_salary\": \"32000.00\", \"employee_id\": 2, \"gross_salary\": \"32000.00\", \"present_days\": 0, \"lop_deduction\": \"0.00\", \"absence_deduction_applied\": false, \"unauthorized_absence_days\": 0}','2026-10-13 16:31:41'),(8,2,'magesh','Admin','employee.created','employee','3','{\"department\": \"IT\", \"designation\": \"Software Developer\", \"employee_code\": \"EMP003\"}','2026-10-13 16:54:29'),(9,4,'pasu','Employee','leave.applied','leave','3','{\"status\": \"Pending\", \"end_date\": \"2026-10-14\", \"leave_type\": \"Casual\", \"start_date\": \"2026-10-14\", \"employee_id\": 3}','2026-10-13 17:01:16'),(10,2,'magesh','Admin','leave.approved','leave','3','{\"status\": \"Approved\", \"end_date\": \"2026-10-14\", \"lop_days\": 0, \"leave_type\": \"Casual\", \"start_date\": \"2026-10-14\", \"employee_id\": 3}','2026-10-13 17:04:56'),(11,2,'magesh','Admin','payroll.generated','payroll','4','{\"year\": 2026, \"month\": 10, \"status\": \"Generated\", \"lop_days\": 0, \"net_salary\": \"25000.00\", \"employee_id\": 3, \"gross_salary\": \"25000.00\", \"present_days\": 0, \"lop_deduction\": \"0.00\", \"absence_deduction_applied\": false, \"unauthorized_absence_days\": 0}','2026-10-13 17:07:11'),(12,2,'magesh','Admin','payroll.locked','payroll','3','{\"year\": 2026, \"month\": 10, \"status\": \"Locked\", \"net_salary\": \"32000.00\", \"employee_id\": 2}','2026-10-13 17:11:12'),(13,2,'magesh','Admin','payroll.locked','payroll','4','{\"year\": 2026, \"month\": 10, \"status\": \"Locked\", \"net_salary\": \"25000.00\", \"employee_id\": 3}','2026-10-13 17:11:46'),(14,2,'magesh','Admin','payroll.credit_simulated','payroll','4','{\"year\": 2026, \"month\": 10, \"status\": \"Paid\", \"net_salary\": \"25000.00\", \"employee_id\": 3, \"payment_type\": \"simulation_only\"}','2026-10-13 17:12:18'),(15,2,'magesh','Admin','employee.document_uploaded','employee_document','1','{\"filename\": \"attendance_report.pdf\", \"size_bytes\": 2282, \"employee_id\": 1, \"content_type\": \"application/pdf\", \"employee_code\": \"EMP001\"}','2026-10-13 17:46:10'),(16,2,'magesh','Admin','attendance.admin_overridden','attendance','1','{\"after\": {\"check_in\": \"2026-10-13T03:30:00+00:00\", \"check_out\": \"2026-10-13T12:30:00+00:00\", \"attendance_date\": \"2026-10-13\"}, \"before\": {\"check_in\": \"2026-10-13T03:10:02+00:00\", \"check_out\": \"2026-10-13T03:10:22+00:00\", \"attendance_date\": \"2026-10-13\"}, \"reason\": \"Corrected attendance after manager verification\", \"employee_id\": 1, \"changed_fields\": [\"check_in\", \"check_out\"]}','2026-10-13 18:07:56'),(17,2,'magesh','Admin','user.role_changed','user','1','{\"new_role\": \"HR\", \"previous_role\": \"Employee\", \"target_user_id\": 1}','2026-10-14 08:49:43'),(18,2,'magesh','Admin','user.role_changed','user','1','{\"new_role\": \"Employee\", \"previous_role\": \"HR\", \"target_user_id\": 1}','2026-10-14 08:54:11'),(19,2,'magesh','Admin','payroll.generated','payroll','5','{\"year\": 2026, \"month\": 9, \"status\": \"Generated\", \"lop_days\": 0, \"net_salary\": \"25000.00\", \"employee_id\": 3, \"gross_salary\": \"25000.00\", \"present_days\": 0, \"lop_deduction\": \"0.00\", \"absence_deduction_applied\": true, \"unauthorized_absence_days\": 0}','2026-10-14 09:10:58'),(20,2,'magesh','Admin','payroll.manually_adjusted','payroll','5','{\"year\": 2026, \"month\": 9, \"reason\": \"Approved performance bonus\", \"employee_id\": 3, \"new_adjustment\": \"1500.00\", \"new_net_salary\": \"26500.00\", \"previous_adjustment\": \"0.00\", \"previous_net_salary\": \"25000.00\"}','2026-10-14 09:12:09'),(21,2,'magesh','Admin','payroll.generated','payroll','6','{\"year\": 2026, \"month\": 9, \"status\": \"Generated\", \"lop_days\": 22, \"net_salary\": \"6666.67\", \"employee_id\": 1, \"gross_salary\": \"25000.00\", \"present_days\": 0, \"lop_deduction\": \"18333.33\", \"absence_deduction_applied\": true, \"unauthorized_absence_days\": 22}','2026-10-14 11:05:00'),(22,2,'magesh','Admin','payroll.manually_adjusted','payroll','6','{\"year\": 2026, \"month\": 9, \"reason\": \"Approved performance bonus\", \"employee_id\": 1, \"new_adjustment\": \"1500.00\", \"new_net_salary\": \"8166.67\", \"previous_adjustment\": \"0.00\", \"previous_net_salary\": \"6666.67\"}','2026-10-14 11:06:14'),(23,1,'suresh','Employee','attendance.checked_in','attendance','2','{\"check_in\": \"2026-10-14T08:39:54.988071+00:00\", \"employee_id\": 1, \"employee_code\": \"EMP001\", \"attendance_date\": \"2026-10-14\"}','2026-10-14 14:09:55');
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `email_logs`
--

DROP TABLE IF EXISTS `email_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `email_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `recipient_email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `template_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `related_entity_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `related_entity_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `sent_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_email_logs_related_entity_type` (`related_entity_type`),
  KEY `ix_email_logs_status` (`status`),
  KEY `ix_email_logs_recipient_email` (`recipient_email`),
  KEY `ix_email_logs_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `email_logs`
--

LOCK TABLES `email_logs` WRITE;
/*!40000 ALTER TABLE `email_logs` DISABLE KEYS */;
INSERT INTO `email_logs` VALUES (1,'pasu@gmail.com','Welcome to PeopleDesk HRMS','employee_onboarding','sent','employee','3',NULL,'2026-10-13 11:24:35','2026-10-13 16:54:35'),(2,'pasu@gmail.com','Leave request pending','leave_notification','sent','leave','3',NULL,'2026-10-13 11:31:24','2026-10-13 17:01:23'),(3,'pasu@gmail.com','Leave request approved','leave_notification','sent','leave','3',NULL,'2026-10-13 11:35:02','2026-10-13 17:05:02'),(4,'yusuf@gmail.com','Payroll update - 10/2026','payroll_notification','sent','payroll','3',NULL,'2026-10-13 11:41:17','2026-10-13 17:11:17'),(5,'pasu@gmail.com','Payroll update - 10/2026','payroll_notification','sent','payroll','4',NULL,'2026-10-13 11:41:52','2026-10-13 17:11:52'),(6,'pasu@gmail.com','Payroll update - 10/2026','payroll_notification','sent','payroll','4',NULL,'2026-10-13 11:42:25','2026-10-13 17:12:24'),(7,'pasu@gmail.com','Salary slip available - 10/2026','salary_slip_notification','sent','payroll','4',NULL,'2026-10-13 11:45:52','2026-10-13 17:15:51'),(8,'pasu@gmail.com','Payroll update - 09/2026','payroll_notification','sent','payroll','5',NULL,'2026-10-14 03:41:06','2026-10-14 09:11:06'),(9,'pasu@gmail.com','Payroll update - 09/2026','payroll_notification','sent','payroll','5',NULL,'2026-10-14 03:42:18','2026-10-14 09:12:17'),(10,'suresh@gmail.com','Payroll update - 09/2026','payroll_notification','sent','payroll','6',NULL,'2026-10-14 05:35:05','2026-10-14 11:05:05'),(11,'suresh@gmail.com','Payroll update - 09/2026','payroll_notification','sent','payroll','6',NULL,'2026-10-14 05:36:20','2026-10-14 11:06:20'),(12,'suresh@gmail.com','Salary slip available - 10/2026','salary_slip_notification','sent','payroll','1',NULL,'2026-10-14 06:15:53','2026-10-14 11:45:52');
/*!40000 ALTER TABLE `email_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `employee_documents`
--

DROP TABLE IF EXISTS `employee_documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `employee_documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `original_filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `stored_filename` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` int NOT NULL,
  `uploaded_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `stored_filename` (`stored_filename`),
  KEY `uploaded_by` (`uploaded_by`),
  KEY `ix_employee_documents_id` (`id`),
  KEY `ix_employee_documents_employee_created` (`employee_id`,`created_at`),
  CONSTRAINT `employee_documents_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE,
  CONSTRAINT `employee_documents_ibfk_2` FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `employee_documents`
--

LOCK TABLES `employee_documents` WRITE;
/*!40000 ALTER TABLE `employee_documents` DISABLE KEYS */;
INSERT INTO `employee_documents` VALUES (1,1,'attendance_report.pdf','975e99b78482402584a0497fa980f379.pdf','application/pdf',2282,2,'2026-10-13 17:46:10');
/*!40000 ALTER TABLE `employee_documents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `employees`
--

DROP TABLE IF EXISTS `employees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `employees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `employee_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `designation` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `joining_date` date NOT NULL,
  `salary` decimal(12,2) NOT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  UNIQUE KEY `ix_employees_employee_code` (`employee_code`),
  KEY `ix_employees_id` (`id`),
  CONSTRAINT `employees_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `employees`
--

LOCK TABLES `employees` WRITE;
/*!40000 ALTER TABLE `employees` DISABLE KEYS */;
INSERT INTO `employees` VALUES (1,1,'EMP001','IT','Software Engineer','2026-03-16',25000.00,'9000000000','Chennai',1,'2026-10-13 08:28:02'),(2,3,'EMP002','IT','QA Engineer','2026-10-13',32000.00,NULL,NULL,0,'2026-10-13 11:23:01'),(3,4,'EMP003','IT','Software Developer','2026-10-13',25000.00,'9876543210','Chennai, Tamil Nadu',1,'2026-10-13 16:54:29');
/*!40000 ALTER TABLE `employees` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `leave_balances`
--

DROP TABLE IF EXISTS `leave_balances`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `leave_balances` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `leave_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `total_days` int NOT NULL,
  `used_days` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_employee_leave_type` (`employee_id`,`leave_type`),
  KEY `ix_leave_balances_id` (`id`),
  KEY `ix_leave_balances_employee_id` (`employee_id`),
  CONSTRAINT `leave_balances_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `leave_balances`
--

LOCK TABLES `leave_balances` WRITE;
/*!40000 ALTER TABLE `leave_balances` DISABLE KEYS */;
INSERT INTO `leave_balances` VALUES (1,1,'Casual',12,3),(2,1,'Sick',12,0),(3,1,'Earned',12,0),(4,1,'Unpaid',0,0),(5,3,'Casual',12,1);
/*!40000 ALTER TABLE `leave_balances` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `leave_requests`
--

DROP TABLE IF EXISTS `leave_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `leave_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `leave_type` enum('Casual','Sick','Earned','Unpaid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `reason` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('Pending','Approved','Rejected') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Pending',
  `lop_days` int NOT NULL,
  `reviewed_by` int DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `reviewed_by` (`reviewed_by`),
  KEY `ix_leave_requests_id` (`id`),
  KEY `ix_leave_requests_employee_id` (`employee_id`),
  CONSTRAINT `leave_requests_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `leave_requests_ibfk_2` FOREIGN KEY (`reviewed_by`) REFERENCES `users` (`id`),
  CONSTRAINT `ck_leave_dates` CHECK ((`end_date` >= `start_date`))
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `leave_requests`
--

LOCK TABLES `leave_requests` WRITE;
/*!40000 ALTER TABLE `leave_requests` DISABLE KEYS */;
INSERT INTO `leave_requests` VALUES (1,1,'Casual','2026-10-20','2026-10-21','Personal work','Approved',0,2,'2026-10-13 03:32:13','2026-10-13 08:48:22'),(2,1,'Casual','2026-10-22','2026-10-22','I visit temple','Approved',0,2,'2026-10-13 09:46:41','2026-10-13 15:15:50'),(3,3,'Casual','2026-10-14','2026-10-14','hospital','Approved',0,2,'2026-10-13 11:34:57','2026-10-13 17:01:16');
/*!40000 ALTER TABLE `leave_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll`
--

DROP TABLE IF EXISTS `payroll`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL,
  `month` int NOT NULL,
  `year` int NOT NULL,
  `monthly_salary` decimal(12,2) NOT NULL,
  `present_days` int NOT NULL,
  `lop_days` int NOT NULL,
  `gross_salary` decimal(12,2) NOT NULL,
  `lop_deduction` decimal(12,2) NOT NULL,
  `net_salary` decimal(12,2) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Generated',
  `is_locked` tinyint(1) NOT NULL,
  `generated_by` int NOT NULL,
  `locked_at` datetime DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `manual_adjustment_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `adjustment_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `adjusted_by` int DEFAULT NULL,
  `adjusted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_employee_payroll_period` (`employee_id`,`month`,`year`),
  KEY `generated_by` (`generated_by`),
  KEY `ix_payroll_employee_id` (`employee_id`),
  KEY `ix_payroll_id` (`id`),
  KEY `fk_payroll_adjusted_by` (`adjusted_by`),
  CONSTRAINT `fk_payroll_adjusted_by` FOREIGN KEY (`adjusted_by`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `payroll_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `payroll_ibfk_2` FOREIGN KEY (`generated_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll`
--

LOCK TABLES `payroll` WRITE;
/*!40000 ALTER TABLE `payroll` DISABLE KEYS */;
INSERT INTO `payroll` VALUES (1,1,10,2026,25000.00,1,0,25000.00,0.00,25000.00,'Paid',1,2,'2026-10-13 05:09:29','2026-10-13 05:10:51','2026-10-13 10:37:20',0.00,NULL,NULL,NULL),(2,1,11,2026,25000.00,0,0,25000.00,0.00,25000.00,'Paid',1,2,'2026-10-13 10:01:51','2026-10-13 10:04:24','2026-10-13 15:30:03',0.00,NULL,NULL,NULL),(3,2,10,2026,32000.00,0,0,32000.00,0.00,32000.00,'Locked',1,2,'2026-10-13 11:41:12',NULL,'2026-10-13 16:31:41',0.00,NULL,NULL,NULL),(4,3,10,2026,25000.00,0,0,25000.00,0.00,25000.00,'Paid',1,2,'2026-10-13 11:41:47','2026-10-13 11:42:19','2026-10-13 17:07:11',0.00,NULL,NULL,NULL),(5,3,9,2026,25000.00,0,0,25000.00,0.00,26500.00,'Generated',0,2,NULL,NULL,'2026-10-14 09:10:58',1500.00,'Approved performance bonus',2,'2026-10-14 03:42:10'),(6,1,9,2026,25000.00,0,22,25000.00,18333.33,8166.67,'Generated',0,2,NULL,NULL,'2026-10-14 11:05:00',1500.00,'Approved performance bonus',2,'2026-10-14 05:36:15');
/*!40000 ALTER TABLE `payroll` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `full_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `hashed_password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_email` (`email`),
  KEY `ix_users_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'suresh','suresh@gmail.com','$argon2id$v=19$m=65536,t=3,p=4$VVzqmSeBtkzzKs9X2mcPoQ$kfjSkSsIihkhiWesscZjK/cXbE0v1k21evqrf8/VfF0','Employee',1,'2026-10-13 08:05:29'),(2,'magesh','magesh@gmail.com','$argon2id$v=19$m=65536,t=3,p=4$C3mTPoRzejlnmXCyygzXnQ$Ymg/iHf4QsKtKhra3HeoT0Yvbw01lDEBgjtC4IJg9rI','Admin',1,'2026-10-13 08:25:41'),(3,'Yusuf','yusuf@gmail.com','$argon2id$v=19$m=65536,t=3,p=4$OXZQopFPqxP8nMVWAOdogw$IRtMGeLAffRL5Zpv1TDms+9oM5d70PqQg7z0KnFCxJ0','Employee',0,'2026-10-13 11:23:01'),(4,'pasu','pasu@gmail.com','$argon2id$v=19$m=65536,t=3,p=4$SsEObFL+x3nXazuDHAdJ+w$3qQVgqrkZES0jQq1UGh2HSdt2jbfYL98+erTyOPfZEE','Employee',1,'2026-10-13 16:51:20');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-15 12:15:01
