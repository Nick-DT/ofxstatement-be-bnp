import csv
import re 
import unicodedata

from ofxstatement import statement
from ofxstatement.parser import CsvStatementParser
from ofxstatement.plugin import Plugin
# from ofxstatement.parser import StatementParser
# from ofxstatement.statement import StatementLine


class bnpPlugin(Plugin):
    """Belgian BNP Paribas Fortis
    """

    def get_parser(self, filename):
        f = open(filename, 'r',encoding='utf-8-sig') #,encoding=self.settings.get("charset", "ISO-8859-1"))##
        parser = bnpParser(f)
        parser.statement.bank_id = "Bnp"
        parser.statement.currency = "EUR"
        return parser


class bnpParser(CsvStatementParser):

    date_format = "%d/%m/%Y"

    mappings = {
        # 'id': 0,
        # 'check_no': 0,
        'date': 1,
        # 'payee': 5,
        'memo': 6,
        'amount': 3
    }

    def parse(self):
        """Main entry point for parsers
        super() implementation will call to split_records and parse_record to
        process the file.
        """
        stmt = super(bnpParser, self).parse()
        statement.recalculate_balance(stmt)
        return stmt

    def split_records(self):
        """Return iterable object consisting of a line per transaction
        """
        reader = csv.reader(self.fin, delimiter=";")
        next(reader, None)
        return reader

    def extract_text_between_card_and_date(self,description):
        # Regular expression to match an obfuscated card number (with X or digits)
        card_pattern = r"[0-9X]{4} [0-9X]{4} [0-9X]{4} [0-9X]{4}"

        # Regular expression to match a date in the format DD/MM/YYYY
        date_pattern = r"\d{2}/\d{2}/\d{4}"

        # Find all matches for card numbers and dates
        card_match = re.search(card_pattern, description)

        if card_match :
            
            # Set start of capture section
            start_index = card_match.end()

            # Now check whether there is a date afterwards
            date_match = re.search(date_pattern, description[start_index:])

            if date_match:
                end_index = start_index + date_match.start()
            else : end_index = len(description)
            
            # Extract the text between the card number and the date or the end of the string
            extracted_text = description[start_index:end_index].strip()

            return extracted_text
        else : return description

    def clean_text_to_ascii(self, textIn):
        # 'Maps left and right single and double quotation marks'
        # 'into ASCII single and double quotation marks'
        punctuation = { 0x2018:0x27, 0x2019:0x27, 0x201C:0x22, 0x201D:0x22 }
        textOut = textIn.translate(punctuation)
        # Now, in order: normalize special chars to use the same code, then encode as ascii byte sequence
        # (should currently be a variation of utf-8), and finally decode to UTF-8 to get back to a string
        textOut = unicodedata.normalize('NFKD',textOut).encode('ascii', 'ignore').decode("UTF-8")

        return textOut

    def parse_record(self, line):
        """Parse given transaction line and return StatementLine object
        """

        stmtline = super(bnpParser, self).parse_record(line)
        
        bnp_trtyp_mapping = { 
            "Paiement par carte"                  : "POS"      ,
            "Ordre permanent"                     : "REPEATPMT"  ,
            "Virement en euros"                   : "XFER"  ,
            "Paiement par carte de crédit"        : "PAYMENT"              ,
            "Frais liés au compte"                : "FEE"      ,
            "Corrections opérations par carte"    : "OTHER"                  ,
            "Intérêts du compte d'épargne"        : "INT"              ,
            "Domiciliation"                       : "DIRECTDEBIT"  ,
            "Virement instantané en euros"        : "XFER"              ,
            "Retrait d'espèces par carte"         : "ATM"              ,
            "Retrait d'espèces à l'étranger"      : "ATM"                  ,
            "Frais de gestion de compte"          : "FEE"              ,
            "Coûts opérations diverses"           : "FEE"          ,
            "Retrait devise étrangère au guichet" : "ATM"                      ,
            "Versement en espèces par carte"      : "DIRECTDEP"                  

        }
        stmtline.trntype = bnp_trtyp_mapping[line[6]]
        # stmtline.trntype = 'DEBIT' if stmtline.amount < 0 else 'CREDIT'
        
        description = self.clean_text_to_ascii(line[10])
        # print(description)
        # Compute proper payee
        payeetxt = self.clean_text_to_ascii(line[8])
        if not payeetxt and line[6].strip().upper()=="PAIEMENT PAR CARTE":
            payeetxt = self.clean_text_to_ascii(self.extract_text_between_card_and_date(description))
        
        # Now if available add the account nb, and if no payee name use account nb instead
        stmtline.payee = self.clean_text_to_ascii(line[7].strip()) # Payee defaults to account nb
        if payeetxt :
            if (not line[7] or re.search(r"^0+", line[7].strip())) : stmtline.payee = payeetxt.strip() # but if empty and name isn't, take the name
            elif line[7] : stmtline.payee = self.clean_text_to_ascii(line[7].strip()) +" - "+ payeetxt.strip()
        
        # Compute proper reference
        bk_id = ""
        if "REFERENCE" in description.upper():
            # Regular expression to match a date in the format DD/MM/YYYY
            start_ref_pattern = r"REFERENCE[^:]+"
            # Regular expression to match a date in the format DD/MM/YYYY
            ref_pattern = r"\b[^\s]+"
            
            ref_start_match = re.search(start_ref_pattern, description.upper())
            
            if ref_start_match :
                ref_match = re.search(ref_pattern, description[ref_start_match.end():])
                bk_id = description[ref_start_match.end()+ref_match.start():ref_start_match.end()+ref_match.end()]
        
        if not bk_id: stmtline.check_no = line[0]
        else :        stmtline.check_no = str(bk_id)     

        # If available, concatenate both the type of transaction and the comm in the same column
        if not line[9] : stmtline.memo = self.clean_text_to_ascii(line[6].strip())
        else : stmtline.memo = self.clean_text_to_ascii(line[6].strip() +" - "+ line[9].strip())
        # print(line[6])
        # print(stmtline.memo)

        # Raise an exception if we have statements for more than one account
        if (self.statement.account_id == None):
            self.statement.account_id = line[5]
        elif (self.statement.account_id != line[5]):
            raise ValueError("CSV file contains multiple accounts")
        
        return stmtline
