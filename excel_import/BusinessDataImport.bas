Attribute VB_Name = "BusinessDataImport"
Option Explicit

Private Const IMPORT_URL As String = "http://127.0.0.1:5055/import-vba"

Public Sub UploadBusinessData()
    Dim jsonPath As String
    Dim responsePath As String
    jsonPath = Environ$("TMPDIR") & "business_data_import_payload.json"
    responsePath = Environ$("TMPDIR") & "business_data_import_response.txt"

    WriteTextFile jsonPath, BuildPayload()

    Dim command As String
    command = "curl -s -X POST -H 'Content-Type: application/json' --data-binary @" & _
              ShellQuote(jsonPath) & " " & ShellQuote(IMPORT_URL) & " > " & ShellQuote(responsePath)
    MacScript "do shell script " & AppleScriptQuote(command)

    ApplyResponse ReadTextFile(responsePath)
    MsgBox "Upload finished. Check Upload_Status and Upload_Error columns.", vbInformation
End Sub

Private Function BuildPayload() As String
    BuildPayload = "{""transection"":" & SheetRowsJson("Transection") & _
                   ",""sotephwar_transection"":" & SheetRowsJson("Sotephwar_Transection") & _
                   ",""financial_obligations"":" & SheetRowsJson("Financial_Obligations") & _
                   ",""sotephwar_inventory"":" & SheetRowsJson("Sotephwar_Inventory") & "}"
End Function

Private Function SheetRowsJson(sheetName As String) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(sheetName)

    Dim statusColumn As Long
    statusColumn = HeaderColumn(ws, "Upload_Status")

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    Dim output As String
    Dim rowNumber As Long
    For rowNumber = 2 To lastRow
        If Trim(CStr(ws.Cells(rowNumber, statusColumn).Value)) = "" And RowHasData(ws, rowNumber) Then
            If Len(output) > 0 Then output = output & ","
            output = output & RowJson(ws, rowNumber)
        End If
    Next rowNumber

    SheetRowsJson = "[" & output & "]"
End Function

Private Function RowHasData(ws As Worksheet, rowNumber As Long) As Boolean
    Dim lastColumn As Long
    lastColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column

    Dim columnNumber As Long
    Dim header As String
    For columnNumber = 1 To lastColumn
        header = Trim(CStr(ws.Cells(1, columnNumber).Value))
        If Left(header, 7) <> "Upload_" Then
            If Trim(CStr(ws.Cells(rowNumber, columnNumber).Value)) <> "" Then
                RowHasData = True
                Exit Function
            End If
        End If
    Next columnNumber

    RowHasData = False
End Function

Private Function RowJson(ws As Worksheet, rowNumber As Long) As String
    Dim lastColumn As Long
    lastColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column

    Dim output As String
    output = """__row_number"":" & CStr(rowNumber)

    Dim columnNumber As Long
    Dim header As String
    For columnNumber = 1 To lastColumn
        header = Trim(CStr(ws.Cells(1, columnNumber).Value))
        If Left(header, 7) <> "Upload_" Then
            output = output & ",""" & JsonEscape(header) & """:""" & JsonEscape(CellText(ws.Cells(rowNumber, columnNumber))) & """"
        End If
    Next columnNumber

    RowJson = "{" & output & "}"
End Function

Private Function CellText(cell As Range) As String
    If IsDate(cell.Value) Then
        If UsesYearDayMonthFormat(cell.NumberFormat) Then
            CellText = Format(DateSerial(Year(cell.Value), Day(cell.Value), Month(cell.Value)), "yyyy-mm-dd")
        Else
            CellText = Format(cell.Value, "yyyy-mm-dd")
        End If
    Else
        CellText = Trim(CStr(cell.Value))
    End If
End Function

Private Function UsesYearDayMonthFormat(numberFormat As String) As Boolean
    Dim fmt As String
    fmt = LCase(numberFormat)
    fmt = Replace(fmt, "\", "")
    fmt = Replace(fmt, "-", "/")
    fmt = Replace(fmt, ".", "/")
    fmt = Replace(fmt, " ", "")
    UsesYearDayMonthFormat = InStr(fmt, "yyyy/dd/mm") > 0 Or InStr(fmt, "yy/dd/mm") > 0
End Function

Private Function HeaderColumn(ws As Worksheet, headerName As String) As Long
    Dim lastColumn As Long
    lastColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column

    Dim columnNumber As Long
    For columnNumber = 1 To lastColumn
        If Trim(CStr(ws.Cells(1, columnNumber).Value)) = headerName Then
            HeaderColumn = columnNumber
            Exit Function
        End If
    Next columnNumber

    Err.Raise 5, , "Missing header " & headerName & " in " & ws.Name
End Function

Private Sub ApplyResponse(responseText As String)
    Dim lines() As String
    lines = Split(responseText, vbLf)

    Dim i As Long
    For i = LBound(lines) To UBound(lines)
        If Trim(lines(i)) <> "" And Trim(lines(i)) <> "OK" Then
            ApplyResponseLine lines(i)
        End If
    Next i
End Sub

Private Sub ApplyResponseLine(lineText As String)
    Dim parts() As String
    parts = Split(lineText, "|")
    If UBound(parts) < 4 Then Exit Sub

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(parts(0))

    Dim rowNumber As Long
    rowNumber = CLng(parts(1))
    If rowNumber < 2 Then Exit Sub

    ws.Cells(rowNumber, HeaderColumn(ws, "Upload_Status")).Value = parts(2)
    ws.Cells(rowNumber, HeaderColumn(ws, "Uploaded_ID")).Value = parts(3)
    ws.Cells(rowNumber, HeaderColumn(ws, "Uploaded_At")).Value = Now
    ws.Cells(rowNumber, HeaderColumn(ws, "Upload_Error")).Value = parts(4)
End Sub

Private Function JsonEscape(value As String) As String
    value = Replace(value, "\", "\\")
    value = Replace(value, Chr(34), "\" & Chr(34))
    value = Replace(value, vbCrLf, "\n")
    value = Replace(value, vbCr, "\n")
    value = Replace(value, vbLf, "\n")
    JsonEscape = value
End Function

Private Function ShellQuote(value As String) As String
    ShellQuote = "'" & Replace(value, "'", "'\''") & "'"
End Function

Private Function AppleScriptQuote(value As String) As String
    AppleScriptQuote = Chr(34) & Replace(value, Chr(34), "\" & Chr(34)) & Chr(34)
End Function

Private Sub WriteTextFile(path As String, text As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open path For Output As #fileNumber
    Print #fileNumber, text
    Close #fileNumber
End Sub

Private Function ReadTextFile(path As String) As String
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open path For Input As #fileNumber
    ReadTextFile = Input$(LOF(fileNumber), fileNumber)
    Close #fileNumber
End Function
