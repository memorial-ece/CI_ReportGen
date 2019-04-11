from Report import Report
from ReportConfig import ReportConfig
from DataStore import DataStore
import grades_org
import globals
import textformatting as tf
import os
import numpy as np
import logging
import re
import pandas as pd

class ReportGenerator(object):
    """Report Generator Class

    Bundles all of the Report object generation things in one place and adds
    convenience methods for generation

    Attributes:
        config: A ReportConfig object
        programs: A list of programs to process
        whitelist: A dictionary including lists of the only things that should
            be processed. Options can include, but are not limited to, lists of:
            - courses
            - indicators
            - assessments
            As long as the whitelist key matches closely to the column name in
            the indicator lookup table, it should be fine
        ds: A DataStore object

        Todo:
            - Implement a blacklisting feature
    """


    def __init__(self, config, year=None, semester=None, programs=None, whitelist=None, ds=None,
            indicators_loc=None, grades_loc=None, histograms_loc=None):
        """Object Initialization

        Args:
            config: A ReportConfig object
            indicators_loc: The location of the indicator sheets. Defaults to
                searching an "Indicators" folder in the directory above the
                project (see ReportConfig documentation for more info)
            grades_loc: The location of the grades sheets. Defaults to searching
                a "Grades" folder in the directory above the project (see
                ReportConfig documentation for more info)
            histograms_loc: The location to store histograms. Defaults to using
                a "Histograms" folder in the directory above the project (see
                ReportConfig documentation for more info)

            year: The academic year that data is being parsed for, or in some cases
                depending on config, the cap year on grade generation. Defaults
                to None
            semester: An integer from 1 to 3 indicating the semester. Defaults
                to None
            programs: A list of programs to generate indicators for. Defaults to
                using all programs
            whitelist: A dictionary of lists, keyed by the only stuff to parse (i.e.
                'course', 'indicator', etc.) and filled with the specific values
                to uniquely parse. Defaults to no whitelist
            ds: A DataStore object. Defaults to generating one based on the
                whitelist entries for 'programs'
        """
        logging.info("Start of AutoGenerator initialization")
        logging.info("Initializing ReportConfig")
        self.config = config

        logging.info("Initializing whitelist")
        self.whitelist = whitelist
        logging.debug("Whitelist: %s", str(self.whitelist))

        logging.info("Initializing program list")
        self.programs = programs
        if not self.programs:
            self.programs = globals.all_programs
        logging.debug("Programs: %s", ', '.join(self.programs))

        # If any of the file location parameters were passed in, overwrite what
        # the ReportConfig object has
        if indicators_loc:
            self.config.indicators_loc = indicators_loc
        if grades_loc:
            self.config.grades_loc = grades_loc
        if histograms_loc:
            self.config.histograms_loc = histograms_loc

        logging.debug("Indicators location is %s", self.config.indicators_loc)
        logging.debug("Grades location is %s", self.config.grades_loc)
        logging.debug("Histograms location is %s", self.config.histograms_loc)

        # Check to see if a DataStore was passed to the function
        if not ds:
            logging.debug("No DataStore object was passed to the function; creating one now")
            self.ds=DataStore(programs=self.programs, indicators_loc=self.config.indicators_loc,
                    grades_loc=self.config.grades_loc)

        # Make sure that the histograms folder exists as the program writes to it
        logging.info("Ensuring that the histograms directory exists")
        os.makedirs(self.config.histograms_loc, exist_ok=True)

        logging.info("ReportGenerator initialization done!")


    def _parse_row(self, row):
        """Turn a row of a Pandas DataFrame into a dictionary and bin list

        The data stored in the master indicator spreadsheets needs to be cleaned up
        properly for a Report to use it. This function does that based on things
        in the ReportConfig.

        - ReportConfig.header_attribs determines what data gets pulled from the
          spreadsheet. For a single entry in header_attribs, multiple values
          could get pulled and concatenated from the spreadsheet row. For example,
          writing just 'Course' in the header_attribs would join the columns
          'Course #' and 'Course Description' using a ' - ' character

        Args:
            row: The row of a Pandas DataFrame (so a Pandas Series) to clean up

        Returns:
            dict: A dictionary containing the indicator information, keyed using instructions
            list(float): The bin ranges that have been converted from a comma-separated string
                to a list of floats. 0 gets appended to the front for NumPy histogram

        Todo:
            - Document the exceptions
        """
        logging.info("Parsing a row from a Pandas DataFrame")
        logging.debug("Row: %s", str(row))
        # Handle the bins first since those are easy
        try:
            bins = [float(x) for x in row['Bins'].split(',')]
        except Exception as exc:
            logging.warning("ERROR: Non-number bins encountered in a lookup table")
            return None, None
        logging.debug("Bins parsed as:\t%s", ', '.join(str(x) for x in bins))

        # Convert the comma-separated string into dictionary keys
        logging.info("Creating a dictionary of indicator information")
        indicator_dict = {i:"" for i in [x.strip() for x in self.config.header_attribs.split(',')]}
        logging.debug("Indicator dictionary keys obtained from following header_attribs: %s",
            ', '.join(self.config.header_attribs.split(',')))
        logging.debug("Indicator dictionary keys: %s", ', '.join(indicator_dict.keys()))

        logging.info("Filling the dictionary with information from the row")
        for key in indicator_dict.keys():
            # Look for all occurrences where the key is found in the row's columns
            # and store that information in a list
            occurrences = [str(row[i]) for i in row.index if key in i]
            # Glue all collected data together with ' - ' characters
            indicator_dict[key] = ' - '.join(occurrences)
            logging.debug("Stored indicator key: %s", key)
            logging.debug("Stored in the indicator entry: %s", indicator_dict[key])

        logging.info("Returning indicator dictionary and bins from this row")
        return indicator_dict, bins


    def autogenerate(self):
        """Begin autogeneration of reports

        Todo:
            - Implement other ways to set up the grades
            - Make get_cohort call less bad
        """
        logging.info("Beginning report autogeneration")

        # If the autogeneration is not plotting grades by year, do different things
        # with the way that autogeneration iterates
        logging.debug("Autogenerator set to plot grades by %s from ReportConfig", self.config.plot_grades_by)
        if self.config.plot_grades_by != 'year':
            # Select a specific indicator sheet to query
            iterprograms = [self.config.use_indicators_from]
        else:
            iterprograms = self.ds.programs
        logging.debug("Autogenerator set up to use programs: %s", ', '.join(iterprograms))

        # Iterate across the list of programs
        for program in iterprograms:
            logging.info("Generating reports for program %s", program)

            logging.info("Getting a query list from the program's indicator lookup table")
            self.ds.query_indicators(program=program, dict_of_queries=self.whitelist)

            # Get a list of files in the program's grades directory so that any
            # special name tags can be taken into consideration. Set up as a
            # dict so that it can be updated using the backup file dict from
            # DataStore
            logging.info("Getting list of grade files in directory %s", self.config.grades_loc + program)
            search_list = {program: os.listdir(self.config.grades_loc + program)}

            logging.info("Creating a list hierarchy to deal with file backup things")
            search_list.update(self.ds.backup_file_lists)

            # Set up a file to store missing data in
            logging.info("Starting a file to save missing data")
            missing_data = open("../Missing Data/{} missing data.txt".format(program), "w+")

            # Iterate across each indicator (each row)
            logging.info("Beginning row iteration...")
            for i, row in self.ds.last_query.iterrows():

                # Skip this row if no bins are defined
                if row['Bins'] in [np.nan, None]:
                    logging.warning("No bins (and likely no data) found for {} {} {} {}, skipping row".format(
                            row['Indicator #'], row['Level'], row['Course #'], row['Method of Assessment']))
                    logging.warning("Missing binning stored in separate file")
                    missing_data.write("Missing bin ranges for {a} {b} ({c}-{d})\n".format(a=row["Course #"],
                            b=row["Method of Assessment"], c=row['Indicator #'], d=row['Level']))
                    continue
                else:
                    logging.debug("Processing data for {} {} {} {}".format(row['Indicator #'], row['Level'],
                        row['Course #'], row['Method of Assessment']))

                # Obtain the necessary indicator data and bins
                indicator_data, bins = self._parse_row(row)
                if not bins:
                    logging.warning("ERROR: No useable bins for {} {} {} {}, skipping row".format(
                            row['Indicator #'], row['Level'], row['Course #'], row['Method of Assessment']
                    ))
                    missing_data.write("No useable bins for {a} {b} ({c}-{d})\n".format(a=row["Course #"],
                            b=row["Method of Assessment"], c=row['Indicator #'], d=row['Level']))
                    continue

                logging.debug("Indicator data obtained from the row: %s", str(indicator_data))

                #-----------------------------------------------------------------------------
                # Get the grades ready for the histogram
                #-----------------------------------------------------------------------------
                logging.info("Organizing the grades for this histogram now")

                # Try to open the grades by searching the file lists using regular expressions
                open_this=None
                for key in search_list.keys():
                    indicator_data['Program'] = key
                    logging.debug("Searching the {} directory for grades for {} {}".format(
                        key,
                        indicator_data['Course'].split('-')[0].strip(),
                        indicator_data['Assessment']
                    ))
                    for file in search_list[key]:
                        # If statement searches the file string for the course
                        # and assessment type
                        x = re.search("{c} {a}".format(
                            c=indicator_data['Course'].split('-')[0].strip(),
                            a=indicator_data['Assessment']
                        ).lower(), file.lower())
                        logging.debug("Search for {} resulted in {}".format(file, x))
                        if x != None:
                            open_this = self.config.grades_loc + key + '/' + file
                            break
                    if open_this != None:
                        break
                logging.debug("Search resulted in %s", str(open_this))

                if self.config.plot_grades_by != 'year':
                    raise NotImplementedError("Attempted to parse grades by a way that isn't year, which is currently not implemented")
                else:
                    try:
                        # Try to open the grade file
                        grades = grades_org.open_grades(row, program, file=open_this)
                    except Exception as exc:
                        logging.warning(str(exc) + '\n' + "Skipping course and continuing")
                        logging.warning("Missing data stored in separate file")
                        missing_data.write("Missing data for {a} {b} ({c}-{d})\n".format(a=row["Course #"],
                            b=row["Method of Assessment"], c=row['Indicator #'], d=row['Level']))
                        continue
                # Rename the DataFrame columns by cohort for now. With new plot
                # configurations, this can become some form of call
                logging.info("Re-organizing the grade columns by changing their year to a cohort message")
                renamed_columns = list()
                for col in grades.columns:
                    # Get the real size of the grade column by stripping out null values
                    figure_out_size = list()
                    for x in grades[col]:
                        if not pd.isnull(x):
                            figure_out_size.append(x)
                    cohort_size = len(figure_out_size)
                    renamed_columns.append("{}COHORT-{} STUDENTS".format(
                        tf.get_cohort(col, course=indicator_data['Course'].split(' - ')[0]),
                        cohort_size
                    ))
                grades.columns = renamed_columns

                # Generate Report and add annotations depending on configuration
                logging.info("Setting up Report object")
                report = Report(indicator_data, bins, self.config)
                report.add_header()
                report.plot(grades)
                if self.config.add_bin_ranges:
                    report.add_bin_ranges()
                if self.config.add_title:
                    report.add_title()

                #------------------------------------------------------------------------
                # Save the report with a specific file name and to a specific location
                #
                # This version of the histogram generator will save histograms to
                # program subfolders in its main save spot. As a result, any
                # previous histograms left there will get overridden with each
                # run of the generator.
                #------------------------------------------------------------------------

                logging.info("Creating a histogram save directory for %s", program)
                os.makedirs(self.config.histograms_loc + program, exist_ok=True)
                report.save(self.config.histograms_loc + "{program}/{GA}-{L} {course} {assess} Report - {cfg}.pdf".format(
                        program = program, GA = indicator_data['Indicator'].split('-')[0].strip(),
                        L = indicator_data['Level'][0], course = indicator_data['Course'].split('-')[0].strip(),
                        assess = indicator_data['Assessment'], cfg = self.config.name
                ))

        logging.info("Autogeneration done!")
